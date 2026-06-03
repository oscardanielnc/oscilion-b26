"""R5 — Exits: TP fijo (tp_r=4) vs TRAILING (ATR), por moneda, en los supervivientes.

¿Dejar correr con trailing supera al TP fijo amplio? Config de entrada FIJA por
estrategia (la validada); solo cambia el exit. OOS = 2025→. Métrica en R.
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np

from config import DATA_DIR
from oscilion.backtest.engine_strat import StratParams, load_bundle, run

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

# (estrategia, moneda, entry_params, max_hold) de los supervivientes/candidatos
ENTRY = {
    "ema_trend_stack": ({"atr_mult_sl": 1.5, "fresh_gate": True, "session_filter": True,
                         "rsi_filter": False}, 60, ["BTC", "BNB", "TRX"]),
    "orb_breakout": ({"range_max_pct": 0.015, "fresh_gate": True, "long_only": False,
                      "session_filter": True}, 24, ["LINK", "DOT", "TRX", "BTC", "ADA", "DOGE"]),
}
SYM = lambda b: f"{b}/USDT:USDT"


def _stats(trades, oos=False):
    t = [x for x in trades if x["entry_ts"] >= SPLIT] if oos else trades
    if not t:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0}
    R = np.array([x["R"] for x in t])
    return {"n": len(t), "exp_R": float(R.mean()),
            "wr": float(np.mean([x["pnl"] > 0 for x in t]))}


def _worker(args):
    strategy, base = args
    entry_p, mh, _coins = ENTRY[strategy]
    b = load_bundle(SYM(base), strategy)
    if b is None:
        return (strategy, base), None
    out = {}
    # TP fijo tp_r=4
    pf = StratParams(strategy=strategy, params={**entry_p, "tp_r": 4.0}, max_hold_signal_bars=mh,
                     exit_mode="fixed_tp")
    out["fixed_tp4"] = run(b, pf)
    # trailing a varios ATR
    for ta in (1.5, 2.0, 3.0):
        pt = StratParams(strategy=strategy, params={**entry_p, "tp_r": 0.0}, max_hold_signal_bars=mh,
                         exit_mode="trailing", trail_atr=ta)
        out[f"trail{ta}"] = run(b, pt)
    return (strategy, base), out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    tasks = [(s, b) for s, (_p, _m, coins) in ENTRY.items() for b in coins]
    t0 = time.time()
    with Pool(processes=min(len(tasks), 12)) as pool:
        res = dict(pool.map(_worker, tasks))
    print(f"[{time.time()-t0:.0f}s]", flush=True)

    L = ["# 🪤 R5 — TP fijo vs trailing, por moneda (supervivientes)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · entrada fija validada · solo cambia el exit · "
         f"OOS=2025→ · exp_R_\n",
         "| Estrategia | Moneda | fixed_tp4 full/OOS | trail1.5 full/OOS | trail2.0 full/OOS | trail3.0 full/OOS |",
         "|---|---|---|---|---|---|"]
    for (strategy, base) in tasks:
        r = res.get((strategy, base))
        if r is None:
            L.append(f"| {strategy} | {base} | — | — | — | — |"); continue
        def cell(key):
            return f"{_stats(r[key])['exp_R']:+.3f}/{_stats(r[key], True)['exp_R']:+.3f}"
        L.append(f"| {strategy} | {base} | {cell('fixed_tp4')} | {cell('trail1.5')} | "
                 f"{cell('trail2.0')} | {cell('trail3.0')} |")
    md = "\n".join(L)
    out = DATA_DIR / "reports" / "r5_exit_check.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
