"""Barrido de universo — buscar combos GANADORES out-of-sample (2026-06-22).

Aplica la config FIJA validada de cada estrategia a TODAS las monedas con histórico
(sin re-tunear por moneda = sin sobreajuste) y juzga por edge OOS robusto en DOS
regímenes independientes:
    - OOS holdout  : entradas >= 2025-01-01 (nunca usado para fijar params).
    - 2026-YTD     : entradas >= 2026-01-01 (régimen más reciente).
Un combo es GANADOR si exp_R >= MIN_EDGE en AMBOS y n_oos >= MIN_N. Doble régimen
positivo ⇒ no es suerte de una ventana.

Salida 1h (screen ancho, todas las monedas) o 15m (rigor pleno, solo las que tienen
15m). El capital solo se despliega sobre combos validados con 15m (ver --tf 15m).

Uso:
    python -m research.universe_scan            # screen 1h, todas
    python -m research.universe_scan --tf 15m   # rigor 15m (solo monedas con 15m)
    python -m research.universe_scan --tf 15m --syms BTC,ETH,...
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import glob
from datetime import datetime, timezone

import numpy as np

from oscilion.backtest.engine_strat import StratParams, load_bundle, run

_H = 3_600_000
SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
Y2026 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

MIN_EDGE = 0.10        # exp_R mínimo por trade en cada régimen OOS
MIN_N = 30             # n mínimo de trades OOS holdout
MIN_N_2026 = 12        # n mínimo en el corte 2026 (más corto)

# Config FIJA por estrategia (validada; NO se re-tunea por moneda) + max_hold (barras señal).
CANON = {
    "ema_trend_stack": (dict(atr_mult_sl=1.5, tp_r=4.0, fresh_gate=True,
                             session_filter=True, rsi_filter=False), 30),
    "orb_breakout":    (dict(range_max_pct=0.015, tp_r=4.0, fresh_gate=True,
                             long_only=False, session_filter=True), 24),
    "vwap_anchor":     (dict(sl_atr_mult=2.0, tp_r=2.5, fresh_gate=True,
                             trend_filter=False, session_filter=False), 120),
    "break_retest":    (dict(vol_max_ratio=1.0, retest_half_atr=0.3, tp_r=0.0,
                             trend_filter=True, long_only=False), 42),
    "momentum_pullback": (dict(impulse_atr_min=0.8, pullback_max=0.8, tp_r=4.0,
                               fresh_gate=True, long_only=True), 60),
}


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": None, "wr": None, "sumR": None}
    R = np.array([t["R"] for t in trades])
    return {"n": len(trades), "exp_R": float(R.mean()),
            "wr": float((R > 0).mean()), "sumR": float(R.sum())}


def _sub(trades, lo, hi):
    return [t for t in trades if lo <= t["entry_ts"] < hi]


def _symbols(tf):
    syms = []
    for d in sorted(glob.glob("data/ohlcv/binanceusdm/*")):
        sym = os.path.basename(d)
        if not os.path.exists(f"{d}/1h.parquet"):
            continue
        if tf != "1h" and not os.path.exists(f"{d}/{tf}.parquet"):
            continue
        syms.append(sym.replace("_USDT_USDT", "") + "/USDT:USDT")
    return syms


def scan(strategy, sym, tf):
    params, mh = CANON[strategy]
    bundle = load_bundle(sym, strategy, exit_tf=tf)
    if bundle is None:
        return None
    trades = run(bundle, StratParams(strategy=strategy, params=params, exit_tf=tf,
                                     max_hold_signal_bars=mh))
    if not trades:
        return None
    t_max = max(t["entry_ts"] for t in trades) + 1
    return {"full": _stats(trades), "oos": _stats(_sub(trades, SPLIT, t_max)),
            "y2026": _stats(_sub(trades, Y2026, t_max))}


def is_winner(r):
    o, y = r["oos"], r["y2026"]
    return (o["exp_R"] is not None and y["exp_R"] is not None
            and o["n"] >= MIN_N and y["n"] >= MIN_N_2026
            and o["exp_R"] >= MIN_EDGE and y["exp_R"] >= MIN_EDGE)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    tf = "1h"
    syms_filter = None
    if "--tf" in sys.argv:
        tf = sys.argv[sys.argv.index("--tf") + 1]
    if "--syms" in sys.argv:
        syms_filter = set(sys.argv[sys.argv.index("--syms") + 1].split(","))
    strategies = list(CANON)

    syms = _symbols(tf)
    if syms_filter:
        syms = [s for s in syms if s.split("/")[0] in syms_filter]

    print(f"Universe scan · tf_salida={tf} · {len(syms)} monedas × {len(strategies)} estrategias "
          f"· filtro: OOS>={MIN_EDGE} Y 2026>={MIN_EDGE}, n_oos>={MIN_N}\n")
    winners = []
    rows = []
    for strat in strategies:
        for sym in syms:
            try:
                r = scan(strat, sym, tf)
            except Exception as e:
                continue
            if r is None:
                continue
            r["sym"], r["strat"] = sym, strat
            rows.append(r)
            if is_winner(r):
                winners.append(r)

    winners.sort(key=lambda r: -(r["oos"]["exp_R"] + r["y2026"]["exp_R"]))
    print(f"=== GANADORES (doble régimen OOS) : {len(winners)} ===")
    print(f"{'COMBO':<28}{'full n/expR':<15}{'OOS n/expR':<15}{'2026 n/expR':<15}{'OOS wr'}")
    for r in winners:
        c = f"{r['sym'].split('/')[0]} {r['strat']}"
        print(f"{c:<28}{r['full']['n']}/{r['full']['exp_R']:+.3f}    "
              f"{r['oos']['n']}/{r['oos']['exp_R']:+.3f}    "
              f"{r['y2026']['n']}/{r['y2026']['exp_R']:+.3f}    {r['oos']['wr']*100:.0f}%")

    # también: combos actuales del portfolio que FALLAN el filtro (para podar)
    from oscilion.strategies.assignment import PORTFOLIO
    cur = {(s.split("/")[0], a.strategy) for s, lst in PORTFOLIO.items() for a in lst}
    win_keys = {(r["sym"].split("/")[0], r["strat"]) for r in winners}
    print(f"\n=== PORTFOLIO ACTUAL que NO pasa el filtro (candidato a podar) ===")
    for r in rows:
        key = (r["sym"].split("/")[0], r["strat"])
        if key in cur and key not in win_keys:
            print(f"{r['sym'].split('/')[0]} {r['strat']:<18} "
                  f"OOS {r['oos']['n']}/{(r['oos']['exp_R'] if r['oos']['exp_R'] is not None else 0):+.3f}  "
                  f"2026 {r['y2026']['n']}/{(r['y2026']['exp_R'] if r['y2026']['exp_R'] is not None else 0):+.3f}")


if __name__ == "__main__":
    main()
