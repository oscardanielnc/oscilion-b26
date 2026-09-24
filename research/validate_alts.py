"""15m + double-OOS + ANTI-BETA validation of candidate combos (2026-06-22).

Adopts the "gold = beta" lesson: a long-only strategy on a trending asset wins by
beta, not alpha. For each combo it reports, besides the OOS exp_R:
  - a LONG / SHORT split (a real edge is not longs-only on an asset that went up),
  - the asset's buy & hold over the window (beta proxy),
  - an ANTI-BETA verdict:
      ALPHA = profitable shorts, or profitable longs with the asset ~flat/falling.
      BETA? = longs only and the asset rallied hard (>+15%): suspected beta.
      MIXED = longs ride some trend but also pay off when flat.

Usage: python -m research.validate_alts [--syms RUNE,NEO,...] [--strats break_retest,vwap_anchor]
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
from oscilion.data import store
from research.universe_scan import CANON, MIN_EDGE, MIN_N, MIN_N_2026

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
Y2026 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
RALLY = 15.0   # buy & hold > +15% over the window = trending asset (beta risk)

DEFAULT_SYMS = ["RUNE", "NEO", "HBAR", "TIA", "ATOM", "FLOW"]
DEFAULT_STRATS = ["break_retest", "vwap_anchor", "orb_breakout", "ema_trend_stack", "momentum_pullback"]


def _e(R):
    return float(np.mean(R)) if len(R) else None


def _buyhold(sym, lo, hi):
    d = store.load_bars(sym, "1h")
    d = d[(d["ts"] >= lo) & (d["ts"] < hi)]
    if len(d) < 2:
        return None
    return (d["close"].iloc[-1] / d["close"].iloc[0] - 1) * 100


def _antibeta(window_trades, bh):
    L = [t["R"] for t in window_trades if t["side"] == "long"]
    S = [t["R"] for t in window_trades if t["side"] == "short"]
    eL, eS = _e(L), _e(S)
    # alpha if the shorts pay off, or if the longs pay off with the asset ~flat/falling
    short_alpha = eS is not None and len(S) >= 5 and eS > 0
    long_on_flat = eL is not None and eL > 0 and (bh is None or bh <= 5.0)
    long_on_rally_only = (not S or eS is None or eS <= 0) and (bh is not None and bh > RALLY)
    if short_alpha or long_on_flat:
        verdict = "ALPHA"
    elif long_on_rally_only:
        verdict = "BETA?"
    else:
        verdict = "MIXED"
    return verdict, (len(L), eL), (len(S), eS)


def main():
    syms = DEFAULT_SYMS
    strats = DEFAULT_STRATS
    if "--syms" in sys.argv:
        syms = sys.argv[sys.argv.index("--syms") + 1].split(",")
    if "--strats" in sys.argv:
        strats = sys.argv[sys.argv.index("--strats") + 1].split(",")
    syms = [s + "/USDT:USDT" for s in syms]

    print(f"15m + double-OOS + anti-beta validation | {len(syms)} coins x {len(strats)} strategies")
    print(f"WINNER = OOS>={MIN_EDGE} AND 2026>={MIN_EDGE}, n_oos>={MIN_N}, and anti-beta != BETA?\n")
    hdr = f"{'COMBO':<26}{'OOS n/expR':<14}{'2026 n/expR':<14}{'L/S 2026':<22}{'b&h26':<9}{'anti-beta':<10}{'VERDICT'}"
    print(hdr); print("-" * len(hdr))
    winners = []
    for strat in strats:
        params, mh = CANON[strat]
        for sym in syms:
            b = load_bundle(sym, strat, exit_tf="15m")
            if b is None:
                continue
            t = run(b, StratParams(strategy=strat, params=params, exit_tf="15m", max_hold_signal_bars=mh))
            if not t:
                continue
            tmax = max(x["entry_ts"] for x in t) + 1
            oos = [x for x in t if SPLIT <= x["entry_ts"] < tmax]
            y26 = [x for x in t if Y2026 <= x["entry_ts"] < tmax]
            eo, ey = _e([x["R"] for x in oos]), _e([x["R"] for x in y26])
            if eo is None or ey is None or len(oos) < MIN_N or len(y26) < MIN_N_2026:
                continue
            bh26 = _buyhold(sym, Y2026, tmax)
            ab, (nl, el), (ns, es) = _antibeta(y26, bh26)
            is_win = eo >= MIN_EDGE and ey >= MIN_EDGE and ab != "BETA?"
            ls = f"L{nl}/{el:+.2f} S{ns}/{es:+.2f}" if es is not None else f"L{nl}/{el:+.2f} S{ns}/-"
            v = "WINNER" if is_win else ("beta-discarded" if ab == "BETA?" else "fails OOS")
            nm = f"{sym.split('/')[0]} {strat}"
            print(f"{nm:<26}{len(oos)}/{eo:+.3f}     {len(y26)}/{ey:+.3f}     {ls:<22}"
                  f"{(f'{bh26:+.0f}%' if bh26 is not None else '-'):<9}{ab:<10}{v}")
            if is_win:
                winners.append((sym, strat, eo, ey, ab))
    print(f"\n=== WINNERS (real alpha, 15m, double OOS): {len(winners)} ===")
    for sym, strat, eo, ey, ab in sorted(winners, key=lambda w: -(w[2] + w[3])):
        print(f"  {sym.split('/')[0]:<6} {strat:<18} OOS{eo:+.3f} / 2026{ey:+.3f}  [{ab}]")


if __name__ == "__main__":
    main()
