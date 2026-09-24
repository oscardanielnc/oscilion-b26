"""Validation audit: purged walk-forward (2026-06-22).

Goal: explain why the gate backtest (+exp_R) does not survive in the forward test.
Isolates TWO sources of inflation on the real PORTFOLIO combos:

  A) SELECTION/IN-SAMPLE LEAK (the gate's):
     forward_results.backtest = run the portfolio's FIXED params over the WHOLE
     history and report exp_R. Those params were chosen by the R2/R3 grid because
     they maximized in-sample -> reporting on the same data. Measured as IS
     (in-sample, < SPLIT) vs OOS holdout (>= SPLIT), SAME fixed params, no re-selection.

  B) UNPURGED WALK-FORWARD LEAK:
     reproduces strat_validation's WF (train [0, te_lo) glued to test [te_lo, te_hi),
     picking the best of ~N configs per fold) and compares it with a PURGED WF:
     train requires exit_ts <= te_lo - embargo (no trade overlapping the test).

Output: a per-combo table with gate(full), IS, OOS holdout, WF naive, WF purged.
Does not touch production. Uses local data (3 years). Metric = exp_R per trade.
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

import numpy as np

from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.strategies.assignment import PORTFOLIO
from research.strat_validation import _grid, _sub

_H = 3_600_000

# Time cuts (UTC). SPLIT separates in-sample / holdout for test A.
SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
# Recent regime: 2026-YTD (closest to the live period).
Y2026 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
# Walk-forward folds (test windows). Expanding train before each one.
WF_BOUNDS = [int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
             for (y, m) in [(2024, 7), (2025, 1), (2025, 7), (2026, 1)]]
MIN_TRAIN = 30


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": None, "wr": None, "sumR": None}
    R = np.array([t["R"] for t in trades])
    return {"n": len(trades), "exp_R": float(R.mean()),
            "wr": float((R > 0).mean()), "sumR": float(R.sum())}


def _run_cfg(bundle, strategy, cfg, mh):
    return run(bundle, StratParams(strategy=strategy, params=cfg, max_hold_signal_bars=mh))


def _wf(runs, bounds, t_max, embargo_ms):
    """Walk-forward: per fold, pick the best cfg on train and evaluate OOS.
    embargo_ms=0 -> naive."""
    pool = []
    for k in range(len(bounds) - 1):
        te_lo, te_hi = bounds[k], bounds[k + 1]
        best, best_tr = None, -1e9
        for _cfg, tr in runs:
            # train: entries before the test; purged requires the exit before te_lo - embargo
            if embargo_ms > 0:
                train = [t for t in tr if t["exit_ts"] <= te_lo - embargo_ms]
            else:
                train = [t for t in tr if t["entry_ts"] < te_lo]
            s = _stats(train)
            if s["n"] >= MIN_TRAIN and s["exp_R"] is not None and s["exp_R"] > best_tr:
                best_tr, best = s["exp_R"], tr
        if best is None:
            continue
        pool.extend([t for t in best if te_lo <= t["entry_ts"] < te_hi])
    return _stats(pool)


def audit_combo(sym, strategy, fixed_params, mh):
    bundle = load_bundle(sym, strategy)
    if bundle is None:
        return None
    # --- A) the portfolio's FIXED params (what the gate runs) ---
    fixed = _run_cfg(bundle, strategy, fixed_params, mh)
    t_max = max((t["entry_ts"] for t in fixed), default=SPLIT + 1) + 1
    gate_full = _stats(fixed)                       # = the gate's forward_results.backtest
    fx_is = _stats(_sub(fixed, 0, SPLIT))           # in-sample
    fx_oos = _stats(_sub(fixed, SPLIT, t_max))      # OOS holdout, SAME params
    fx_2026 = _stats(_sub(fixed, Y2026, t_max))     # recent regime 2026-YTD
    # --- B) full grid for the WF (per-fold selection) ---
    runs = [(cfg, _run_cfg(bundle, strategy, cfg, mh)) for cfg in _grid(strategy)]
    bounds_naive = WF_BOUNDS + [t_max]
    embargo = mh * _H                               # no train trade overlaps the test
    wf_naive = _wf(runs, bounds_naive, t_max, embargo_ms=0)
    wf_purged = _wf(runs, bounds_naive, t_max, embargo_ms=embargo)
    return {"sym": sym, "strategy": strategy, "n_cfgs": len(runs),
            "gate_full": gate_full, "fx_is": fx_is, "fx_oos": fx_oos, "fx_2026": fx_2026,
            "wf_naive": wf_naive, "wf_purged": wf_purged}


def _fmt(s):
    if not s or s["exp_R"] is None:
        return f"{s['n'] if s else 0}/-"
    return f"{s['n']}/{s['exp_R']:+.3f}"


def main():
    combos = []
    for sym, lst in PORTFOLIO.items():
        for a in lst:
            combos.append((sym, a.strategy, a.params, a.max_hold_signal_bars))
    # optional strategy filter: python -m research.purged_wf break_retest,vwap_anchor
    if len(sys.argv) > 1:
        want = set(sys.argv[1].split(","))
        combos = [c for c in combos if c[1] in want]

    split_day = datetime.fromtimestamp(SPLIT / 1000, tz=timezone.utc).date()
    print(f"Purged WF audit | {len(combos)} combos | SPLIT={split_day} "
          f"| folds={len(WF_BOUNDS)} | embargo=max_hold\n")
    hdr = (f"{'COMBO':<26}{'GATE full':<13}{'OOS hold':<13}{'2026-YTD':<13}"
           f"{'WF naive':<13}{'WF PURGED':<13}{'leak'}")
    print(hdr); print("-" * len(hdr))
    rows = []
    for sym, strat, params, mh in combos:
        r = audit_combo(sym, strat, params, mh)
        if r is None:
            print(f"{sym.split('/')[0]+' '+strat:<26}no bundle"); continue
        rows.append(r)
        gate = r["gate_full"]["exp_R"]
        purg = r["wf_purged"]["exp_R"]
        leak = (gate - purg) if (gate is not None and purg is not None) else None
        name = f"{sym.split('/')[0]} {strat}"
        print(f"{name:<26}{_fmt(r['gate_full']):<13}{_fmt(r['fx_oos']):<13}{_fmt(r['fx_2026']):<13}"
              f"{_fmt(r['wf_naive']):<13}{_fmt(r['wf_purged']):<13}{(f'{leak:+.3f}' if leak is not None else '-')}")

    # aggregate summary (equal-weighted per combo with data)
    def col(key):
        xs = [r[key]["exp_R"] for r in rows if r[key]["exp_R"] is not None]
        return (np.median(xs), sum(1 for x in xs if x > 0), len(xs)) if xs else (None, 0, 0)
    print("\nSummary (median exp_R | #positive/#valid):")
    for k, lab in [("gate_full", "GATE full (what it trusts)"), ("fx_oos", "OOS holdout (fixed params)"),
                   ("fx_2026", "2026-YTD (recent regime)"),
                   ("wf_naive", "WF naive (R2/R3)"), ("wf_purged", "WF PURGED (honest)")]:
        m, npos, ntot = col(k)
        print(f"  {lab:<30} {m:+.3f}   {npos}/{ntot} positive" if m is not None else f"  {lab}: -")


if __name__ == "__main__":
    main()
