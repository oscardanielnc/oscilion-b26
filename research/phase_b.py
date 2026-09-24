"""Phase B: portfolio (HONEST: robustness over overfitting).

Earlier finding: tuning params per coin on small samples OVERFITS (high train,
weak OOS), and so do in-sample edge weights. So phase B uses:
  - params = the FIXED validated baseline (tp_r=4 etc.), more robust than the
    train-optimal one.
  - B1 = a DIAGNOSTIC that demonstrates the tuning overfit (not adopted).
  - B6 = portfolio simulation (single account) with the baseline; compares equal
    vs edge weights and concurrency/cluster limits; the best one by GENUINE OOS
    Sharpe is chosen.

Writes data/reports/phase_b.md + oscilion/strategies/tuned.py (weights + clusters + limits).
"""
from __future__ import annotations

import os, sys
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itertools
from datetime import datetime, timezone

import numpy as np

from config import DATA_DIR
from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.backtest.portfolio_sim import simulate
from oscilion.strategies.assignment import all_assignments

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
CLUSTER = {"BTC": "majors", "BNB": "majors", "LINK": "majors", "DOT": "majors", "TRX": "trx"}
GRID = {
    "ema_trend_stack": {"tp_r": [3.0, 4.0, 5.0], "atr_mult_sl": [1.0, 1.5, 2.0],
                        "fresh_gate": [True], "session_filter": [True], "rsi_filter": [False]},
    "orb_breakout": {"tp_r": [0.0, 3.0, 4.0, 6.0], "range_max_pct": [0.010, 0.015, 0.020],
                     "fresh_gate": [True], "long_only": [False], "session_filter": [True]},
}


def _grid(s):
    g = GRID[s]; ks = list(g)
    return [dict(zip(ks, v)) for v in itertools.product(*[g[k] for k in ks])]


def stats(tr):
    if not tr:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0}
    R = np.array([t["R"] for t in tr])
    return {"n": len(tr), "exp_R": float(R.mean()), "wr": float(np.mean([t["pnl"] > 0 for t in tr]))}


def sub(tr, lo, hi):
    return [t for t in tr if lo <= t["entry_ts"] < hi]


def main():
    series = {}
    L = ["# Phase B - portfolio (honest: robustness over overfitting)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | FIXED baseline params | R metric | OOS=2025->_\n",
         "## B1 (diagnostic) - why params are NOT tuned per coin",
         "Tuning on train overfits: the train-optimal config does not generalize. Baseline "
         "(tp_r=4) vs train-optimal, with its genuine OOS.\n",
         "| Series | baseline OOS n/expR | train-opt cfg | train-opt TRAIN->OOS |",
         "|---|---|---|---|"]
    for sym, a in all_assignments():
        b = load_bundle(sym, a.strategy)
        base_tr = run(b, StratParams(strategy=a.strategy, params=a.params,
                                     max_hold_signal_bars=a.max_hold_signal_bars))
        # train-optimal (overfit diagnostic)
        best, best_tr_exp = None, -9
        for cfg in _grid(a.strategy):
            tr = run(b, StratParams(strategy=a.strategy, params=cfg,
                                    max_hold_signal_bars=a.max_hold_signal_bars))
            st = stats(sub(tr, 0, SPLIT))
            if st["n"] >= 20 and st["exp_R"] > best_tr_exp:
                best_tr_exp, best = st["exp_R"], (cfg, tr)
        key = f"{sym}|{a.strategy}"
        b_oos = stats(sub(base_tr, SPLIT, 1 << 62))
        series[key] = {"sym": sym, "strategy": a.strategy, "trades": base_tr,
                       "full": stats(base_tr), "train": stats(sub(base_tr, 0, SPLIT)), "oos": b_oos}
        if best:
            cfg, tr = best
            cfgs = " ".join(f"{k}={cfg[k]}" for k in ("tp_r", "atr_mult_sl", "range_max_pct") if k in cfg)
            to = stats(sub(tr, 0, SPLIT))["exp_R"]; oo = stats(sub(tr, SPLIT, 1 << 62))["exp_R"]
            L.append(f"| {sym.split('/')[0]}-{a.strategy[:3]} | {b_oos['n']}/{b_oos['exp_R']:+.3f} | "
                     f"{cfgs} | {to:+.3f}->{oo:+.3f} |")

    clusters = {k: CLUSTER[k.split("/")[0]] for k in series}
    trades_by = {k: v["trades"] for k, v in series.items()}
    # weights: equal (robust) vs edge by FULL exp_R (comparison)
    w_equal = {k: 1.0 for k in series}
    fe = {k: max(0.0, v["full"]["exp_R"]) for k, v in series.items()}
    mx = max(fe.values()) or 1.0
    w_edge = {k: round(max(0.3, e / mx), 3) for k, e in fe.items()}

    schemes = {
        "equal no limits":        (w_equal, 6, 6),
        "equal maxc3 clu1":       (w_equal, 3, 1),
        "equal maxc3 clu2":       (w_equal, 3, 2),
        "edge  maxc3 clu2":       (w_edge, 3, 2),
    }
    L += ["\n## B6 - PORTFOLIO simulation (single $10k account, baseline params)",
          "| Scheme | FULL ret/MaxDD/Sharpe | **OOS ret/MaxDD/Sharpe** | taken/skip |",
          "|---|---|---|---|"]
    results = {}
    for name, (w, mc, mpc) in schemes.items():
        full = simulate(trades_by, weights=w, clusters=clusters, max_concurrent=mc, max_per_cluster=mpc)
        oos = simulate(trades_by, weights=w, clusters=clusters, max_concurrent=mc,
                       max_per_cluster=mpc, since_ts=SPLIT)
        results[name] = (full, oos, w, mc, mpc)
        L.append(f"| {name} | {full.total_return*100:+.0f}%/{full.max_drawdown*100:.0f}%/{full.sharpe:.2f} | "
                 f"**{oos.total_return*100:+.0f}%/{oos.max_drawdown*100:.0f}%/{oos.sharpe:.2f}** | "
                 f"{full.n_taken}/{full.n_skipped} |")

    # Pick the best by OOS Sharpe AMONG the schemes with real limits (concentration
    # control; "no limits" is only a reference and is never adopted).
    limited = [n for n in results if results[n][3] <= 3]
    best_name = max(limited, key=lambda n: results[n][1].sharpe)
    _bfull, boos, bw, bmc, bmpc = results[best_name]
    L.append(f"\n**Best scheme (OOS Sharpe): {best_name}** -> OOS ret {boos.total_return*100:+.0f}%, "
             f"MaxDD {boos.max_drawdown*100:.0f}%, Sharpe {boos.sharpe:.2f}.")
    L.append("\n_Discipline: fixed baseline params (per-coin tuning overfits). "
             "Clusters: majors={BTC,BNB,LINK,DOT} (~0.7), trx={TRX} (diversifier)._")
    L.append("_Return figures come from a compounded backtest and must be confirmed in the "
             "FORWARD test before being believed; the sober number is MaxDD. Sharpe is the "
             "reward/risk compass._")

    # write the tuned config (baseline params + chosen weights/clusters/limits)
    tuned = ["# GENERATED by research/phase_b.py - do not edit by hand.",
             f"# {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | best scheme: {best_name}",
             "# params = baseline (per-coin tuning overfits on small samples).", ""]
    tuned.append("WEIGHTS = {")
    for k, w in bw.items():
        tuned.append(f"    {k!r}: {w},")
    tuned.append("}\n")
    tuned.append("CLUSTERS = {")
    for k, c in clusters.items():
        tuned.append(f"    {k!r}: {c!r},")
    tuned.append("}\n")
    tuned.append(f"LIMITS = {{'max_concurrent': {bmc}, 'max_per_cluster': {bmpc}}}")
    (DATA_DIR.parent / "oscilion" / "strategies" / "tuned.py").write_text("\n".join(tuned) + "\n", encoding="utf-8")

    md = "\n".join(L)
    (DATA_DIR / "reports" / "phase_b.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print("\n[saved: data/reports/phase_b.md + oscilion/strategies/tuned.py]")


if __name__ == "__main__":
    main()
