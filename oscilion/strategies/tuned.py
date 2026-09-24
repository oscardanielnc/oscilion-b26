# Generated/curated after the 2026-06-22 audit (purged walk-forward + universe sweep
# + 15m anti-beta validation of alts). Scheme validated in phase B: equal weight,
# maxc=3, cluster=2 (tuning per-coin weights overfits on small samples).
# Only combos WITH capital go here (observe combos never get capital nor count
# against the limit).
#
# Clusters = correlation control for "max N per cluster". With 17 combos and only 3
# concurrent positions, splitting by family FORCES diversification (not 3 of a kind):
#   trx      -> 4 strategies on TRX (the per-symbol veto already leaves one alive).
#   altlong  -> long-biased (orb/vwap mean-rev) on correlated major alts.
#   altbreak -> two-sided break_retest on alts (wins on the SHORT side in drops;
#               anti-correlated with the longs -> a strong diversifier).
#   gold     -> gold, uncorrelated with crypto.

# DEMOTE 06-29: the whole vwap_anchor family (long-only continuation) moved from
# capital to observe. Live, it bled -11R buying bull traps on falling alts with no
# regime gate. It returns to capital only if it proves a positive forward with the
# market regime filter on. Capital combos drop from 17 to 12.
WEIGHTS = {
    'TRX/USDT:USDT|ema_trend_stack': 1.0,
    'TRX/USDT:USDT|orb_breakout': 1.0,
    'TRX/USDT:USDT|break_retest': 1.0,
    'LINK/USDT:USDT|orb_breakout': 1.0,
    'XRP/USDT:USDT|orb_breakout': 1.0,
    'DOGE/USDT:USDT|orb_breakout': 1.0,
    'RUNE/USDT:USDT|break_retest': 1.0,
    'NEO/USDT:USDT|break_retest': 1.0,
    'FLOW/USDT:USDT|break_retest': 1.0,
    'HBAR/USDT:USDT|break_retest': 1.0,
    'PAXG/USDT:USDT|break_retest': 1.0,
    'XAU/USDT:USDT|momentum_pullback': 1.0,
}

CLUSTERS = {
    'TRX/USDT:USDT|ema_trend_stack': 'trx',
    'TRX/USDT:USDT|orb_breakout': 'trx',
    'TRX/USDT:USDT|break_retest': 'trx',
    'LINK/USDT:USDT|orb_breakout': 'altlong',
    'XRP/USDT:USDT|orb_breakout': 'altlong',
    'DOGE/USDT:USDT|orb_breakout': 'altlong',
    'RUNE/USDT:USDT|break_retest': 'altbreak',
    'NEO/USDT:USDT|break_retest': 'altbreak',
    'FLOW/USDT:USDT|break_retest': 'altbreak',
    'HBAR/USDT:USDT|break_retest': 'altbreak',
    'PAXG/USDT:USDT|break_retest': 'gold',
    'XAU/USDT:USDT|momentum_pullback': 'gold',
}

# max_concurrent 3 -> 4 (research/concurrency_sweep.py, 2026-06-22): with 17 combos the
# cap of 3 was the bottleneck. 4 DOMINATED 3 in that backtest OOS: more throughput,
# better Sharpe (1.78 vs 1.18) AND lower MaxDD (-61% vs -70%). Above 4, Sharpe drops
# and DD rises.
LIMITS = {'max_concurrent': 4, 'max_per_cluster': 2}
