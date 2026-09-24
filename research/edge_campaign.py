"""Edge validation campaign (the project's go/no-go decision for range reversion).

Runs the honest backtest over 12 coins x 3 years (1h), comparing the naive logic
vs the one with turn confirmation, and breaks down temporal stability (per
semester), per symbol, per regime and parameter sensitivity. Parallel per symbol.

Output: data/reports/edge_campaign_<tf>.md + a console summary.
"""
from __future__ import annotations

import os

# CRITICAL (before importing numpy): 1 BLAS thread per process. With multiprocessing
# (12 workers) and multithreaded BLAS (24 cores) there would be 12x24 threads =
# thrashing -> hang.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys

# allow running as a standalone script: add the project root to the path
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
# set from the CLI (see main); module globals so the Windows Pool inherits them
TF = "1h"
MAX_HOLD = 72


def _configs() -> dict[str, BTParams]:
    return {
        "naive (no turn confirmation)": BTParams(require_confirmation=False, max_hold_bars=MAX_HOLD),
        "confirm (turn confirmation)": BTParams(require_confirmation=True, max_hold_bars=MAX_HOLD),
        "confirm + range-only": BTParams(require_confirmation=True, max_hold_bars=MAX_HOLD,
                                         allow_regimes=("range",)),
    }


def _worker(args):
    sym, tf, params = args   # tf/params are pickled from the parent (Windows spawn-safe)
    return sym, backtest_symbol(sym, tf, params)


def run_config(name: str, params: BTParams) -> list[dict]:
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        results = pool.map(_worker, [(s, TF, params) for s in SYMBOLS])
    pooled = []
    for _sym, trades in results:
        pooled.extend(trades)
    pooled.sort(key=lambda x: x["exit_ts"])
    return pooled


def _semester(ts_ms: int) -> str:
    d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return f"{d.year}-H{1 if d.month <= 6 else 2}"


def main() -> None:
    global TF, MAX_HOLD

    import argparse

    ap = argparse.ArgumentParser(prog="edge_campaign")
    ap.add_argument("--tf", default="1h")
    ap.add_argument("--max-hold", type=int, default=72)
    args = ap.parse_args()
    TF, MAX_HOLD = args.tf, args.max_hold

    L: list[str] = []
    L.append("# Edge validation campaign - Oscilion")
    L.append(f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | 12 coins x 3 years | "
             f"{TF} | max_hold={MAX_HOLD} | capital ${CAPITAL:,.0f} | risk 2%/trade | RR>=2.5_\n")

    pooled_by_cfg: dict[str, list[dict]] = {}
    L.append("## 1) Configuration comparison (pooled, net of costs)")
    L.append("| Config | N | Winrate | PF | Exp/trade | Return | MaxDD | Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, params in _configs().items():
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] starting '{name}' ...", flush=True)
        pooled = run_config(name, params)
        pooled_by_cfg[name] = pooled
        s = metrics.summarize(pooled, CAPITAL)
        L.append(f"| {name} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% | "
                 f"{s['max_drawdown']*100:.1f}% | {s['sharpe']:.2f} |")
        print(f"[{time.time()-t0:.0f}s] {name}: N={s['n']} PF={s['profit_factor']:.2f} "
              f"Sharpe={s['sharpe']:.2f} ret={s['total_return']*100:.1f}%", flush=True)

    primary = pooled_by_cfg["confirm (turn confirmation)"]
    dfp = pd.DataFrame(primary)

    L.append("\n## 2) Per symbol (config: turn confirmation)")
    L.append("| Symbol | N | Winrate | PF | Exp/trade | Return | Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for sym, g in dfp.groupby("sym"):
        s = metrics.summarize(g.to_dict("records"), CAPITAL)
        L.append(f"| {sym} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% | {s['sharpe']:.2f} |")

    L.append("\n## 3) Temporal stability - per semester (confirm)")
    L.append("| Semester | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    dfp["sem"] = dfp["exit_ts"].apply(_semester)
    for sem, g in dfp.groupby("sem"):
        s = metrics.trade_stats(g.to_dict("records"))
        L.append(f"| {sem} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% |")

    L.append("\n## 4) Per regime (confirm)")
    L.append("| Regime | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for reg, g in dfp.groupby("regime"):
        s = metrics.trade_stats(g.to_dict("records"))
        L.append(f"| {reg} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% |")

    L.append("\n## 5) Calibration (confirm) - does the score hold up?")
    L.append("| Bucket | N | Winrate | Mean return |")
    L.append("|---|---:|---:|---:|")
    for b in metrics.calibration(primary):
        L.append(f"| {b['bucket']}-{b['bucket']+10} | {b['n']} | {b['winrate']*100:.1f}% | "
                 f"{b['avg_ret_pct']*100:.3f}% |")

    exits = dfp["exit_reason"].value_counts().to_dict()
    L.append("\n_Exits (confirm): " + ", ".join(f"{k}={v}" for k, v in exits.items()) + "_")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / f"edge_campaign_{TF}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[saved to {out}]", flush=True)


if __name__ == "__main__":
    main()
