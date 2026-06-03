"""Probe decisivo: ¿el edge está en momentum (continuación) en vez de reversión?

Compara reversión-con-giro vs momentum/breakout-con-confirmación sobre 12
monedas × 3 años (1h), neto de costos. Si momentum es claramente positivo →
PIVOT real. Si ambos pierden → no hay estructura explotable → descartar.
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

import pandas as pd

from config import DATA_DIR
from oscilion.backtest import metrics
from oscilion.backtest.engine import BTParams, backtest_symbol

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]
CAPITAL = 10_000.0

CONFIGS = {
    "momentum + confirm": BTParams(require_confirmation=True, strategy="momentum",
                                   allow_regimes=("range", "trend", "chaos")),
    "momentum + brk>=1ATR (score>=100)": BTParams(require_confirmation=True, strategy="momentum",
                                                  min_score=100.0,
                                                  allow_regimes=("range", "trend", "chaos")),
}


def _worker(args):
    sym, params = args
    return sym, backtest_symbol(sym, "1h", params)


def run_config(params):
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = pool.map(_worker, [(s, params) for s in SYMBOLS])
    pooled = []
    for _s, t in res:
        pooled.extend(t)
    pooled.sort(key=lambda x: x["exit_ts"])
    return pooled


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L = ["# 🧪 Probe reversión vs momentum — Oscilion",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas × 3 años · 1h · "
         f"neto de costos_\n",
         "## Pooled (neto de costos)",
         "| Estrategia | N | Winrate | PF | Exp/trade | Retorno | MaxDD | Sharpe |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    pooled_by = {}
    for name, p in CONFIGS.items():
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        pooled = run_config(p)
        pooled_by[name] = pooled
        s = metrics.summarize(pooled, CAPITAL)
        L.append(f"| {name} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% | "
                 f"{s['max_drawdown']*100:.1f}% | {s['sharpe']:.2f} |")
        print(f"[{time.time()-t0:.0f}s] {name}: N={s['n']} PF={s['profit_factor']:.2f} "
              f"exp={s['expectancy_pct']*100:.3f}% Sharpe={s['sharpe']:.2f}", flush=True)

    # detalle de momentum: por símbolo, semestral, calibración
    mom = pooled_by["momentum + confirm"]
    df = pd.DataFrame(mom)
    L.append("\n## Momentum — por símbolo")
    L.append("| Símbolo | N | Winrate | PF | Exp/trade | Retorno |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for sym, g in df.groupby("sym"):
        s = metrics.summarize(g.to_dict("records"), CAPITAL)
        L.append(f"| {sym} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% |")

    L.append("\n## Momentum — semestral")
    L.append("| Semestre | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    df["sem"] = df["exit_ts"].apply(
        lambda ms: (lambda d: f"{d.year}-H{1 if d.month <= 6 else 2}")(
            datetime.fromtimestamp(ms / 1000, tz=timezone.utc)))
    for sem, g in df.groupby("sem"):
        s = metrics.trade_stats(g.to_dict("records"))
        L.append(f"| {sem} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% |")

    L.append("\n## Momentum — calibración")
    L.append("| Bucket | N | Winrate | Ret medio |")
    L.append("|---|---:|---:|---:|")
    for b in metrics.calibration(mom):
        L.append(f"| {b['bucket']}-{b['bucket']+10} | {b['n']} | {b['winrate']*100:.1f}% | "
                 f"{b['avg_ret_pct']*100:.3f}% |")
    exits = df["exit_reason"].value_counts().to_dict()
    L.append(f"\n_Salidas (momentum): " + ", ".join(f"{k}={v}" for k, v in exits.items()) + "_")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "momentum_probe.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
