"""Coin -> strategy map: the portfolio the live monitor runs (v1 pilot).

Decided on 2026-06-03 (see docs/STRATEGY_MAP.md). Each coin gets ONLY the
strategies that were validated for it on the honest engine (full + OOS +
walk-forward). Conviction over quantity: without a proven edge, the coin is not here.

The `params` are the fixed, validated pilot config. Do not hardcode new assumptions
without validating them on the honest engine + forward test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Assign:
    strategy: str
    params: dict
    max_hold_signal_bars: int
    conviction: str                 # high | medium | observe
    note: str = ""
    observe_only: bool = False      # True = forward test WITHOUT capital (alerts + stats, weight 0)


# -----------------------------------------------------------------------------
# PORTFOLIO v2 (2026-06-22), rebuilt from the purged walk-forward audit + universe
# sweep (research/purged_wf.py, research/universe_scan.py). CAPITAL RULE: a combo
# only gets capital if its exp_R is >= +0.10 in TWO independent OOS regimes
# (holdout >2025 AND 2026-YTD) with n_oos >= 30. Positive in both regimes => not
# the luck of one window. FIXED config per strategy (re-tuning per coin overfits on
# small samples). Each `note` reads: OOS holdout / 2026-YTD.
# -----------------------------------------------------------------------------

# FIXED validated configs (identical to the ones that passed the OOS sweep).
_EMA  = dict(atr_mult_sl=1.5, tp_r=4.0, fresh_gate=True, session_filter=True, rsi_filter=False)
_ORB  = dict(range_max_pct=0.015, tp_r=4.0, fresh_gate=True, long_only=False, session_filter=True)
_VWAP = dict(sl_atr_mult=2.0, tp_r=2.5, fresh_gate=True, trend_filter=False, session_filter=False)
_BRET = dict(vol_max_ratio=1.0, retest_half_atr=0.3, tp_r=0.0, trend_filter=True, long_only=False)
_MOM  = dict(impulse_atr_min=0.8, pullback_max=0.8, tp_r=4.0, fresh_gate=True, long_only=True)


def _ema(conv, note="", max_hold=30, observe=False):
    return Assign("ema_trend_stack", dict(_EMA), max_hold,
                  "observe" if observe else conv, note=note, observe_only=observe)


def _orb(conv, note="", observe=False):
    return Assign("orb_breakout", dict(_ORB), 24,
                  "observe" if observe else conv, note=note, observe_only=observe)


def _vwap(conv, note="", observe=False):
    return Assign("vwap_anchor", dict(_VWAP), 120,
                  "observe" if observe else conv, note=note, observe_only=observe)


def _bret(conv, note="", observe=False):
    return Assign("break_retest", dict(_BRET), 42,
                  "observe" if observe else conv, note=note, observe_only=observe)


def _mom(conv, note="", observe=False):
    return Assign("momentum_pullback", dict(_MOM), 60,
                  "observe" if observe else conv, note=note, observe_only=observe)


# CORE with capital: 12 combos, both OOS regimes >= +0.10 (15m, real costs).
PORTFOLIO: dict[str, list[Assign]] = {
    # TRX = the edge engine (4 strategies pass; the per-symbol veto keeps one alive at a time)
    "TRX/USDT:USDT":  [_vwap("high", observe=True, note="OOS+0.318 / 2026+0.851; DEMOTE 06-29: long-only vwap bled -11R live with no regime gate -> observe until it proves forward with the filter on"),
                       _ema("high",  "OOS+0.127 / 2026+0.989"),
                       _orb("high",  "OOS+0.336 / 2026+0.445"),
                       _bret("high", "OOS+0.190 / 2026+0.569; promoted to capital")],
    "LINK/USDT:USDT": [_orb("high",  "OOS+0.368 / 2026+0.387")],
    "XRP/USDT:USDT":  [_orb("medium", "OOS+0.162 / 2026+0.233; replaces vwap (negative)")],
    "DOGE/USDT:USDT": [_orb("medium", "OOS+0.114 / 2026+0.400; replaces vwap (negative)")],
    "BNB/USDT:USDT":  [_vwap("medium", observe=True, note="OOS+0.153 / 2026+0.116; DEMOTE 06-29 vwap -> observe"),
                       _ema("medium", observe=True, note="OOS+0.358 strong but 2026+0.049 weak -> observe")],
    "AVAX/USDT:USDT": [_vwap("medium", observe=True, note="OOS+0.104 / 2026+0.154; DEMOTE 06-29 vwap (-3.77R live) -> observe")],
    # Alts validated 2026-06-22 (15m + double OOS + ANTI-BETA). break_retest on falling
    # alts = edge on the SHORT side (these alts fell -26%/-68% in 2026 and the strategy
    # won by shorting -> alpha, not beta). vwap = mean-rev long on a flat/falling asset.
    "RUNE/USDT:USDT": [_bret("high", "OOS+0.318 / 2026+1.069; shorts win (RUNE -29%) = alpha")],
    "NEO/USDT:USDT":  [_bret("high", "OOS+0.126 / 2026+1.023; shorts +1.22 (NEO -38%) = alpha")],
    "FLOW/USDT:USDT": [_bret("high", "OOS+0.337 / 2026+0.175; shorts win (FLOW -68%) = alpha")],
    "HBAR/USDT:USDT": [_bret("medium", "OOS+0.192 / 2026+0.153; shorts (HBAR -26%) = alpha")],
    "TIA/USDT:USDT":  [_vwap("medium", observe=True, note="OOS+0.155 / 2026+0.271; DEMOTE 06-29 vwap -> observe (whole vwap family to observe)")],
    "ATOM/USDT:USDT": [_vwap("medium", observe=True, note="OOS+0.119 / 2026+0.249; DEMOTE 06-29 vwap -> observe")],
    # GOLD, uncorrelated with crypto. break_retest = alpha (shorts +3.0R with flat gold in
    # 2026; not beta). Long-only ema was riding gold's +41% rally (beta) -> observe.
    "PAXG/USDT:USDT": [_bret("high", "GOLD OOS+0.469 / 2026+1.847; anti-beta OK (shorts win)"),
                       _ema("medium", observe=True,
                            note="GOLD: long-only rode gold +41% (beta); flat 2026 only +0.23 -> observe")],
    "XAU/USDT:USDT":  [_mom("medium", "GOLD spot OOS+0.151 / 2026+0.250; flat gold -> mild alpha")],

    # OBSERVE (no capital): they pass one regime but fail the other. They keep producing
    # stats and graduate on their own through the gate if they confirm. No capital at risk.
    "BTC/USDT:USDT":  [_ema("medium", observe=True, note="2026+0.411 strong / OOS+0.025 weak -> observe"),
                       _orb("medium", observe=True, note="candidate; watch")],
    "ETH/USDT:USDT":  [_vwap("medium", observe=True, note="OOS+0.111 / 2026+0.041 marginal -> observe")],
    "DOT/USDT:USDT":  [_orb("medium", observe=True, note="OOS+0.106 / 2026-0.069 recent failure -> observe")],
}

# PRUNED (negative in BOTH OOS regimes: no edge, removed from the portfolio):
#   BTC vwap_anchor  (OOS-0.014 / 2026-0.041)
#   DOGE vwap_anchor (OOS-0.234 / 2026-0.186)
#   XRP vwap_anchor  (OOS-0.249 / 2026-0.257)


def core_symbols() -> list[str]:
    return list(PORTFOLIO.keys())


def assignments_for(sym: str) -> list[Assign]:
    return PORTFOLIO.get(sym, [])


def all_assignments() -> list[tuple[str, Assign]]:
    return [(sym, a) for sym, lst in PORTFOLIO.items() for a in lst]
