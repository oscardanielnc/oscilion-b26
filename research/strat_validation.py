"""R2: honest PER-COIN validation of the strategies ported from the earlier project.

For each strategy x coin (12 coins, 3 years, honest engine with pessimistic 15m
exits + real costs):
  1) DEFAULT params -> train/test (unbiased anchor).
  2) Parameter SWEEP -> the best is chosen ONLY on train and reported on test
     (honest OOS selection).
  3) WALK-FORWARD -> per fold the config is chosen on its train and evaluated on
     its test; OOS trades are pooled. Primary verdict.

No blind averaging (BTC-correlated coins would dominate): results are reported per
coin and, for the summary, as an equal-weighted vote (each coin counts once).
Primary metric: expectancy per trade in R.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itertools
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
WF_BOUNDS = [int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
             for (y, m) in [(2024, 7), (2025, 1), (2025, 7), (2026, 1)]]

GRIDS = {
    "momentum_pullback": {
        "impulse_atr_min": [0.6, 0.8, 1.0, 1.2],
        "pullback_max": [0.6, 0.8],
        "tp_r": [1.5, 2.0, 3.0, 4.0],
        "fresh_gate": [True, False],
        "long_only": [True, False],
    },
    "ema_trend_stack": {
        "atr_mult_sl": [1.0, 1.5],
        "tp_r": [2.0, 3.0, 4.0],
        "fresh_gate": [True, False],
        "session_filter": [True, False],
        "rsi_filter": [True, False],
    },
    "orb_breakout": {
        "range_max_pct": [0.010, 0.015, 0.020],
        "tp_r": [0.0, 3.0, 4.0, 6.0],            # 0 = no TP (runs until SL/timeout)
        "fresh_gate": [True, False],
        "long_only": [True, False],
        "session_filter": [True, False],
    },
    "break_retest": {
        "vol_max_ratio": [1.0, 1.5],
        "retest_half_atr": [0.3, 0.5],
        "tp_r": [0.0, 2.0, 3.0],
        "trend_filter": [True, False],
        "long_only": [True, False],
    },
    "vwap_anchor": {
        "sl_atr_mult": [1.5, 2.0, 2.5],
        "tp_r": [0.0, 2.0, 2.5, 4.0],            # 0 = no TP (runs until SL/timeout)
        "fresh_gate": [True, False],
        "trend_filter": [True, False],
        "session_filter": [True, False],
    },
}
DEFAULTS = {
    "momentum_pullback": {"impulse_atr_min": 0.8, "pullback_max": 0.8, "tp_r": 2.0,
                          "fresh_gate": True, "long_only": True},
    "ema_trend_stack": {"atr_mult_sl": 1.0, "tp_r": 2.0, "fresh_gate": True,
                        "session_filter": True, "rsi_filter": False},
    "orb_breakout": {"range_max_pct": 0.015, "tp_r": 0.0, "fresh_gate": True,
                     "long_only": False, "session_filter": True},
    "break_retest": {"vol_max_ratio": 1.0, "retest_half_atr": 0.3, "tp_r": 0.0,
                     "trend_filter": True, "long_only": False},
    "vwap_anchor": {"sl_atr_mult": 2.0, "tp_r": 2.5, "fresh_gate": True,
                    "trend_filter": False, "session_filter": False},
}
MAXHOLD = {"momentum_pullback": 60, "ema_trend_stack": 60, "orb_breakout": 24,
           "break_retest": 42, "vwap_anchor": 120}      # 1h x 120 = 5 days
MIN_TRAIN = 30
MIN_WF = 30


def _grid(strategy):
    g = GRIDS[strategy]
    keys = list(g)
    return [dict(zip(keys, vals)) for vals in itertools.product(*[g[k] for k in keys])]


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0, "pf": 0.0, "sumR": 0.0}
    R = np.array([t["R"] for t in trades])
    pnl = np.array([t["pnl"] for t in trades])
    gw = pnl[pnl > 0].sum(); gl = -pnl[pnl <= 0].sum()
    return {"n": len(trades), "exp_R": float(R.mean()), "wr": float((pnl > 0).mean()),
            "pf": float(gw / gl) if gl > 0 else float("inf"), "sumR": float(R.sum())}


def _sub(trades, lo, hi):
    return [t for t in trades if lo <= t["entry_ts"] < hi]


def _label(cfg):
    return " ".join(f"{k}={cfg[k]}" for k in sorted(cfg))


def _worker(args):
    sym, strategy = args
    bundle = load_bundle(sym, strategy)
    if bundle is None:
        return sym, None
    configs = _grid(strategy)
    mh = MAXHOLD[strategy]
    # run each config ONCE over the 3 years (causal), then slice by date
    runs = []
    for cfg in configs:
        trades = run(bundle, StratParams(strategy=strategy, params=cfg, max_hold_signal_bars=mh))
        runs.append((cfg, trades))
    t_max = max((t["entry_ts"] for _c, tr in runs for t in tr), default=SPLIT + 1) + 1

    default_cfg = DEFAULTS[strategy]
    default_trades = next((tr for c, tr in runs if c == default_cfg), [])
    def_full = _stats(default_trades)
    def_train = _stats(_sub(default_trades, 0, SPLIT))
    def_test = _stats(_sub(default_trades, SPLIT, t_max))

    # sweep: choose on train, report on test
    best, best_train = None, -1e9
    for cfg, tr in runs:
        s = _stats(_sub(tr, 0, SPLIT))
        if s["n"] >= MIN_TRAIN and s["exp_R"] > best_train:
            best_train, best = s["exp_R"], (cfg, tr)
    sweep = None
    if best is not None:
        cfg, tr = best
        sweep = {"cfg": _label(cfg), "train": _stats(_sub(tr, 0, SPLIT)),
                 "test": _stats(_sub(tr, SPLIT, t_max))}

    # walk-forward: per fold choose on train (< fold), evaluate on the fold test
    wf_pool = []
    wf_folds = []
    bounds = WF_BOUNDS + [t_max]
    for k in range(len(bounds) - 1):
        te_lo, te_hi = bounds[k], bounds[k + 1]
        bestf, bestf_tr = None, -1e9
        for cfg, tr in runs:
            s = _stats(_sub(tr, 0, te_lo))
            if s["n"] >= MIN_TRAIN and s["exp_R"] > bestf_tr:
                bestf_tr, bestf = s["exp_R"], (cfg, tr)
        if bestf is None:
            continue
        cfg, tr = bestf
        sub = _sub(tr, te_lo, te_hi)
        wf_pool.extend(sub)
        wf_folds.append({"from": datetime.fromtimestamp(te_lo / 1000, tz=timezone.utc).strftime("%Y-%m"),
                         "cfg": _label(cfg), **_stats(sub)})
    wf = _stats(wf_pool)

    return sym, {"def_full": def_full, "def_train": def_train, "def_test": def_test,
                 "sweep": sweep, "wf": wf, "wf_folds": wf_folds}


def _verdict(r):
    """Per-coin verdict (primary = walk-forward OOS)."""
    if r is None:
        return "-", "no data"
    wf = r["wf"]; dt = r["def_test"]
    if wf["n"] < MIN_WF:
        return "N/A", f"WF n={wf['n']}<{MIN_WF}"
    if wf["exp_R"] >= 0.05 and dt["exp_R"] > 0:
        return "PASS", "WF + default OOS positive"
    if wf["exp_R"] > 0:
        return "MARGINAL", "WF OOS marginal"
    return "FAIL", "WF OOS <= 0"


def main():
    L = ["# R2 - Honest per-coin validation (strategies rescued from the earlier project)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | 12 coins | 3 years | honest engine "
         f"(2h/4h signal, pessimistic 15m exit) | real taker costs | metric = expectancy per trade in R_\n",
         "_Default = the original YAML params (unbiased). Sweep = best on TRAIN -> reported on TEST. "
         "WF = 4-fold walk-forward, config chosen per fold on its train, pooled OOS (primary verdict)._\n"]

    strategies = sys.argv[1].split(",") if len(sys.argv) > 1 else ["ema_trend_stack", "momentum_pullback"]
    all_res = {}
    for strategy in strategies:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {strategy} ...", flush=True)
        with Pool(processes=min(len(SYMBOLS), 12)) as pool:
            res = dict(pool.map(_worker, [(s, strategy) for s in SYMBOLS]))
        all_res[strategy] = res
        print(f"  [{time.time()-t0:.0f}s] done", flush=True)

        L.append(f"## {strategy}")
        L.append("| Coin | Verdict | def full n/expR | def TEST n/expR | sweep TEST n/expR | **WF OOS n/expR/WR** | best WF cfg (last fold) |")
        L.append("|---|:--:|---|---|---|---|---|")
        survivors = []
        for sym in SYMBOLS:
            r = res.get(sym)
            v, _why = _verdict(r)
            if r is None:
                L.append(f"| {sym} | - | - | - | - | - | - |")
                continue
            df, dt = r["def_full"], r["def_test"]
            sw = r["sweep"]; wf = r["wf"]
            sw_s = f"{sw['test']['n']}/{sw['test']['exp_R']:+.3f}" if sw else "-"
            last_cfg = r["wf_folds"][-1]["cfg"] if r["wf_folds"] else "-"
            L.append(f"| {sym} | {v} | {df['n']}/{df['exp_R']:+.3f} | {dt['n']}/{dt['exp_R']:+.3f} | "
                     f"{sw_s} | **{wf['n']}/{wf['exp_R']:+.3f}/{wf['wr']*100:.0f}%** | {last_cfg} |")
            if v in ("PASS", "MARGINAL"):
                survivors.append((sym, v, wf["exp_R"], wf["n"]))

        # equal-weighted summary (one vote per coin)
        wfs = [res[s]["wf"]["exp_R"] for s in SYMBOLS if res.get(s) and res[s]["wf"]["n"] >= MIN_WF]
        npos = sum(1 for x in wfs if x > 0)
        med = float(np.median(wfs)) if wfs else 0.0
        L.append(f"\n_Summary {strategy}: coins with a valid WF OOS={len(wfs)}, positive={npos}, "
                 f"median exp_R (equal-weighted)={med:+.3f}. Survivors (PASS/MARGINAL): "
                 f"{', '.join(s.split('/')[0]+f' ({v},{r:+.3f},n={n})' for s,v,r,n in survivors) or 'none'}._\n")

    md = "\n".join(L)
    tag = "r2" if set(strategies) == {"ema_trend_stack", "momentum_pullback"} else "r3_" + "_".join(strategies)
    out = DATA_DIR / "reports" / f"{tag}_strat_validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[saved to {out}]", flush=True)


if __name__ == "__main__":
    main()
