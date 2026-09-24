"""OUT-OF-SAMPLE validation of the breakout (is the pivot real or data snooping?).

The breakout threshold (>= X * ATR) is chosen ONLY on training data and evaluated
on data the selection never saw:
  1) Anchored split: train (2023 -> 2024) vs test (2025 -> 2026).
  2) Walk-forward: expanding train, 6-month test windows; all OOS trades are
     pooled (each fold with the threshold chosen on its own train).

Per-trade metrics (PF, winrate, expectancy), without the pooled-equity artifact.
Each threshold is backtested once over the 3 years (in parallel).
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

from config import DATA_DIR
from oscilion.backtest import metrics
from oscilion.backtest.engine import BTParams, backtest_symbol

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]
THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
MIN_TRAIN = 150  # minimum train trades for a threshold to be considered


def _ms(y: int, m: int) -> int:
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _worker(args):
    sym, t = args
    p = BTParams(strategy="momentum", require_confirmation=True,
                 allow_regimes=("range", "trend", "chaos"), min_breakout_atr=t)
    return backtest_symbol(sym, "1h", p)


def run_threshold(t: float) -> list[dict]:
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = pool.map(_worker, [(s, t) for s in SYMBOLS])
    out = []
    for tr in res:
        out.extend(tr)
    return out


def _subset(trades, lo, hi):
    return [tr for tr in trades if lo <= tr["entry_ts"] < hi]


def _stats(trades):
    return metrics.trade_stats(trades) if trades else {"n": 0, "winrate": 0,
                                                        "profit_factor": 0, "expectancy_pct": 0}


def _select(trades_by_t, lo, hi):
    """Pick the threshold that maximizes expectancy in [lo, hi) (with n >= MIN_TRAIN)."""
    scored = {}
    for t, trs in trades_by_t.items():
        scored[t] = _stats(_subset(trs, lo, hi))
    elig = [(t, s) for t, s in scored.items() if s["n"] >= MIN_TRAIN]
    if not elig:
        elig = list(scored.items())
    return max(elig, key=lambda kv: kv[1]["expectancy_pct"])[0]


def _row(label, s):
    return (f"| {label} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
            f"{s['expectancy_pct']*100:.3f}% |")


def main():
    trades_by_t: dict[float, list[dict]] = {}
    for t in THRESHOLDS:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] backtest threshold {t} ATR ...", flush=True)
        trades_by_t[t] = run_threshold(t)
        print(f"  [{time.time()-t0:.0f}s] {len(trades_by_t[t])} trades", flush=True)

    L = ["# Breakout OOS validation - Oscilion",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | 12 coins x 3 years | 1h | "
         f"momentum + confirm | net of costs | per-trade metrics_\n"]

    all_ts = [tr["entry_ts"] for trs in trades_by_t.values() for tr in trs]
    t_min, t_max = min(all_ts), max(all_ts) + 1

    # --- 1) train vs test grid (split anchored at 2025-01) ---
    split = _ms(2025, 1)
    L.append("## 1) Grid per threshold - train (->2024-12) vs test (2025->)")
    L.append("| ATR threshold | tr N | tr PF | tr exp | **te N** | **te PF** | **te exp** |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for t in THRESHOLDS:
        tr_s = _stats(_subset(trades_by_t[t], t_min, split))
        te_s = _stats(_subset(trades_by_t[t], split, t_max))
        L.append(f"| {t} | {tr_s['n']} | {tr_s['profit_factor']:.2f} | {tr_s['expectancy_pct']*100:.3f}% "
                 f"| {te_s['n']} | {te_s['profit_factor']:.2f} | {te_s['expectancy_pct']*100:.3f}% |")

    # --- 2) anchored split: choose on train, report test ---
    t_star = _select(trades_by_t, t_min, split)
    train_s = _stats(_subset(trades_by_t[t_star], t_min, split))
    test_s = _stats(_subset(trades_by_t[t_star], split, t_max))
    L.append(f"\n## 2) Anchored split - threshold chosen on TRAIN = **{t_star} ATR**")
    L.append("| Period | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    L.append(_row("TRAIN (->2024-12)", train_s))
    L.append(_row("**TEST (2025->2026, OOS)**", test_s))

    # --- 3) walk-forward (expanding train, 6m test; pooled OOS) ---
    bounds = [_ms(2024, 7), _ms(2025, 1), _ms(2025, 7), _ms(2026, 1), t_max]
    L.append("\n## 3) Walk-forward - threshold chosen per fold on its train; OOS test")
    L.append("| Fold (test) | threshold* | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|---:|")
    oos_pool = []
    for i in range(len(bounds) - 1):
        te_lo, te_hi = bounds[i], bounds[i + 1]
        tsel = _select(trades_by_t, t_min, te_lo)          # train = everything before
        sub = _subset(trades_by_t[tsel], te_lo, te_hi)
        oos_pool.extend(sub)
        s = _stats(sub)
        lbl = datetime.fromtimestamp(te_lo / 1000, tz=timezone.utc).strftime("%Y-%m")
        L.append(f"| from {lbl} | {tsel} | {s['n']} | {s['winrate']*100:.1f}% | "
                 f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% |")
    pool_s = _stats(oos_pool)
    L.append(_row("**OOS POOL (walk-forward)**", pool_s))

    ok_anchored = test_s["profit_factor"] > 1.0 and test_s["expectancy_pct"] > 0
    ok_wf = pool_s["profit_factor"] > 1.0 and pool_s["expectancy_pct"] > 0
    if ok_anchored and ok_wf:
        verd = "EDGE CONFIRMED OOS (positive in the anchored split AND walk-forward)"
    elif ok_anchored or ok_wf:
        verd = "PARTIAL EDGE (positive in one of the two OOS tests), fragile"
    else:
        verd = "NOT confirmed OOS (likely data snooping): the edge does not survive"
    L.append(f"\n## OOS verdict: {verd}")
    L.append(f"- Anchored split TEST: PF {test_s['profit_factor']:.2f}, exp {test_s['expectancy_pct']*100:.3f}%")
    L.append(f"- Walk-forward POOL: PF {pool_s['profit_factor']:.2f}, exp {pool_s['expectancy_pct']*100:.3f}%")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "breakout_oos.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[saved to {out}]", flush=True)


if __name__ == "__main__":
    main()
