"""R2b — ¿la ejecución maker y el 'dejar correr ganadores' rescatan el edge?

Config FIJA por estrategia (sin selección por moneda → sin sesgo de overfit),
informada por el walk-forward (tp_r alto). Compara, POR MONEDA, expectativa en R
en el período OOS (2025→) bajo ejecución taker vs maker-entry (techo optimista,
sin modelo de no-fill — eso es R4). Aísla el efecto de la ejecución.
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

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]
SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

# config fija "v2" (deja correr ganadores), informada por el WF
FIXED = {
    "ema_trend_stack": {"atr_mult_sl": 1.5, "tp_r": 4.0, "fresh_gate": True,
                        "session_filter": True, "rsi_filter": False},
    "momentum_pullback": {"impulse_atr_min": 1.0, "pullback_max": 0.6, "tp_r": 4.0,
                          "fresh_gate": True, "long_only": True},
}


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0}
    R = np.array([t["R"] for t in trades])
    pnl = np.array([t["pnl"] for t in trades])
    return {"n": len(trades), "exp_R": float(R.mean()), "wr": float((pnl > 0).mean())}


def _oos(trades):
    return _stats([t for t in trades if t["entry_ts"] >= SPLIT])


def _full(trades):
    return _stats(trades)


def _worker(args):
    sym, strategy = args
    b = load_bundle(sym, strategy)
    if b is None:
        return sym, None
    cfg = FIXED[strategy]
    tk = run(b, StratParams(strategy=strategy, params=cfg, maker_entry=False))
    mk = run(b, StratParams(strategy=strategy, params=cfg, maker_entry=True))
    return sym, {"taker_full": _full(tk), "taker_oos": _oos(tk),
                 "maker_full": _full(mk), "maker_oos": _oos(mk)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L = ["# 🛠️ R2b — Ejecución (taker vs maker) + deja-correr-ganadores, por moneda",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · config FIJA por estrategia (tp_r=4) · "
         f"sin selección por moneda · OOS = 2025→ · maker = techo optimista (sin no-fill)_\n"]

    for strategy in ("ema_trend_stack", "momentum_pullback"):
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {strategy} ...", flush=True)
        with Pool(processes=min(len(SYMBOLS), 12)) as pool:
            res = dict(pool.map(_worker, [(s, strategy) for s in SYMBOLS]))
        print(f"  [{time.time()-t0:.0f}s]", flush=True)

        L.append(f"## {strategy}  (config fija: {FIXED[strategy]})")
        L.append("| Moneda | full taker expR | OOS taker n/expR/WR | OOS **maker** expR | lift maker |")
        L.append("|---|---:|---|---:|---:|")
        pos_tk = pos_mk = 0
        lifts = []
        for sym in SYMBOLS:
            r = res.get(sym)
            if r is None:
                L.append(f"| {sym} | — | — | — | — |"); continue
            to, mo, tf = r["taker_oos"], r["maker_oos"], r["taker_full"]
            lift = mo["exp_R"] - to["exp_R"]
            lifts.append(lift)
            pos_tk += to["exp_R"] > 0
            pos_mk += mo["exp_R"] > 0
            flag = " ✅" if mo["exp_R"] > 0 and to["exp_R"] > 0 else (" 🟡" if mo["exp_R"] > 0 else "")
            L.append(f"| {sym} | {tf['exp_R']:+.3f} | {to['n']}/{to['exp_R']:+.3f}/{to['wr']*100:.0f}% | "
                     f"{mo['exp_R']:+.3f}{flag} | {lift:+.3f} |")
        L.append(f"\n_OOS positivas: taker={pos_tk}/12, maker={pos_mk}/12. "
                 f"Lift maker medio (equiponderado)={np.mean(lifts):+.3f}R/trade._\n")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "r2b_exec_check.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
