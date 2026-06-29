"""Régimen de mercado (beta del benchmark) — fuente única live+backtest (06-29).
Verifica la clasificación close>EMA y que `bull_at` NO mire al futuro.
"""
import numpy as np
import pandas as pd

from oscilion.features import market_regime as mr

_H = 3_600_000


def _bars(closes, tf_h=1):
    n = len(closes)
    ts = np.arange(n) * tf_h * _H
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"ts": ts, "open": c, "high": c, "low": c,
                         "close": c, "volume": np.ones(n)})


def test_regime_alcista_vs_bajista():
    # rampa creciente larga → close por encima de su EMA → alcista al final
    up = _bars(list(range(1, 200)))
    assert mr.latest_bull(up, tf_h=1, ema_len=50) is True
    # rampa decreciente → bajista al final
    down = _bars(list(range(200, 1, -1)))
    assert mr.latest_bull(down, tf_h=1, ema_len=50) is False


def test_regime_sin_datos_es_none():
    assert mr.latest_bull(_bars([1, 2, 3]), tf_h=1, ema_len=50) is None
    assert mr.bull_at(np.array([]), np.array([], dtype=bool), 123) is None


def test_bull_at_sin_lookahead():
    closes = list(range(1, 120))
    close_ts, bull = mr.regime_series(_bars(closes), tf_h=1, ema_len=50)
    # antes del cierre de la primera barra de régimen → None (no inventa pasado)
    assert mr.bull_at(close_ts, bull, int(close_ts[0]) - 1) is None
    # en t = cierre exacto de una barra → usa ESA barra (cierre ≤ t), no la siguiente
    idx = 70
    assert mr.bull_at(close_ts, bull, int(close_ts[idx])) == bool(bull[idx])
    # un instante antes del cierre idx → usa la barra previa
    assert mr.bull_at(close_ts, bull, int(close_ts[idx]) - 1) == bool(bull[idx - 1])
