"""Smoke tests — blindaje mínimo para crecer sin romper.

Puros (sin red ni BD): cazan archivos faltantes/sintaxis (el bug de .gitignore
que ocultó oscilion/data/ habría salido aquí en un checkout limpio), la invariante
de riesgo, el resampleo causal y que las estrategias no crashean.
"""
import importlib
import pkgutil

import numpy as np
import pandas as pd

import oscilion


def test_all_modules_import():
    """Importa TODOS los submódulos de oscilion (falla si falta algún archivo)."""
    failed = []
    for m in pkgutil.walk_packages(oscilion.__path__, "oscilion."):
        try:
            importlib.import_module(m.name)
        except Exception as e:  # noqa: BLE001
            failed.append((m.name, repr(e)))
    assert not failed, f"Módulos que no importan: {failed}"


def test_data_package_present():
    """oscilion.data debe existir (regresión del bug de .gitignore)."""
    import oscilion.data.fetch  # noqa: F401
    import oscilion.data.store  # noqa: F401


def test_risk_invariant():
    """Stop 2% → L y RR exactos; pérdida al stop = 2% del margen."""
    from oscilion.risk import sizing
    m = sizing.compute("long", entry=100, stop=98, tp=105)
    assert abs(m.stop_pct - 0.02) < 1e-9
    assert abs(m.rr - 2.5) < 1e-9 and m.tradeable
    ps = sizing.position_size(1000, m.stop_pct)
    assert abs(ps["risk_amount"] - 20) < 1e-9


def test_resample_causal():
    """1h→4h: agrega bien y DESCARTA el bucket incompleto (sin look-ahead)."""
    from oscilion.backtest.resample import resample_ohlcv
    h = 3_600_000
    df = pd.DataFrame([{"ts": i * h, "open": i, "high": i + 2, "low": i - 1,
                        "close": i + 1, "volume": 1} for i in range(9)])  # 9 velas
    out = resample_ohlcv(df, 4)
    assert len(out) == 2                       # 8 completas → 2 buckets; la 9na se descarta
    assert out.iloc[0]["open"] == 0 and out.iloc[0]["close"] == 4
    assert out.iloc[0]["high"] == 5 and out.iloc[0]["low"] == -1


def test_strategies_no_crash():
    """Las estrategias del núcleo no explotan con un contexto sintético."""
    from oscilion.strategies import library as S
    n = 120
    a = lambda v: np.full(n, v, dtype=float)  # noqa: E731
    tf = S.TFArrays(ts=np.arange(n) * 4 * 3_600_000, open=a(100), high=a(101),
                    low=a(99), close=a(100), volume=a(1), ema9=a(102), ema21=a(101),
                    ema50=a(100), atr=a(1), rsi=a(50), vwap=a(100))
    ctx = S.Ctx(sig=tf, sig_tf_h=4, aux={1: tf, 4: tf})
    for name in ("ema_trend_stack", "orb_breakout", "momentum_pullback", "break_retest"):
        out = S.REGISTRY[name]["fn"](ctx, n - 1, {})
        assert out is None or "side" in out


def test_universe_single_source():
    """config.symbols deriva del núcleo de assignment (fuente única)."""
    import os
    if os.getenv("OSCILION_SYMBOLS"):
        return  # override por env: no aplica
    from config import config
    from oscilion.strategies.assignment import core_symbols
    assert set(config.symbols) == set(core_symbols())
