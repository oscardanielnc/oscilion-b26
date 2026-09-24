"""Process guards (FORWARD_REVIEW 06-10): gate, symbol veto, stale signal, tp runner,
stop floor. Pure (no network, no DB): they make sure the bleeding of the first
cycle (DOGE/vwap n=1 twice, double TRX position, tp=1e18) cannot happen again.
"""
import math

from oscilion.live import guards
from oscilion.strategies.library import tp_barrier


# ------------------------------ validation gate ------------------------------
def test_gate_observe_only_never_gets_capital():
    obs, reason = guards.gate_decision({"n": 999, "exp_r": 1.0}, True, min_n=30, min_exp_r=0.0)
    assert obs and "observe_only" in reason


def test_gate_without_local_backtest_blocks():
    obs, reason = guards.gate_decision(None, False, min_n=30, min_exp_r=0.0)
    assert obs and "no local backtest" in reason


def test_gate_small_n_blocks():
    """The DOGE/vwap case from the first cycle: local backtest n=1 -> never capital."""
    obs, reason = guards.gate_decision({"n": 1, "exp_r": -3.46}, False, min_n=30, min_exp_r=0.0)
    assert obs and "n=1" in reason


def test_gate_negative_exp_r_blocks():
    obs, reason = guards.gate_decision({"n": 100, "exp_r": -0.05}, False, min_n=30, min_exp_r=0.0)
    assert obs and "exp_R" in reason


def test_gate_validated_combo_passes():
    obs, reason = guards.gate_decision({"n": 135, "exp_r": 0.357}, False, min_n=30, min_exp_r=0.0)
    assert not obs and reason is None


# ------------------- ADAPTIVE gate: forward kill / graduation (06-29) -------------------
_KW = dict(min_n=30, min_exp_r=0.0, fw_kill_n=15, fw_kill_exp_r=-0.10,
           fw_grad_n=20, fw_grad_exp_r=0.10)


def test_gate_forward_kill_cuts_capital():
    """Capital combo (backtest OK) whose REAL forward already bleeds -> observe."""
    obs, reason = guards.gate_decision({"n": 100, "exp_r": 0.3}, False,
                                       fw_stats={"n": 20, "exp_r": -0.2}, **_KW)
    assert obs and "forward kill" in reason


def test_gate_forward_kill_ignores_small_n():
    """Negative forward but not enough sample -> the backtest decides (capital)."""
    obs, reason = guards.gate_decision({"n": 100, "exp_r": 0.3}, False,
                                       fw_stats={"n": 5, "exp_r": -0.9}, **_KW)
    assert not obs and reason is None


def test_gate_graduation_observe_to_capital():
    """Observe combo whose REAL forward confirms edge with margin -> promoted."""
    obs, reason = guards.gate_decision({"n": 100, "exp_r": 0.3}, True,
                                       fw_stats={"n": 25, "exp_r": 0.2}, **_KW)
    assert not obs and reason is None


def test_gate_graduation_needs_strong_forward():
    obs, _ = guards.gate_decision({"n": 100, "exp_r": 0.3}, True,
                                  fw_stats={"n": 25, "exp_r": 0.05}, **_KW)
    assert obs                                    # exp_R < grad -> stays observe
    obs2, _ = guards.gate_decision(None, True, fw_stats={"n": 5, "exp_r": 0.9}, **_KW)
    assert obs2                                   # n < grad -> stays observe


# ------------------- recency-aware ROBUST gate (06-29) -------------------
_RW = dict(min_n=30, min_exp_r=0.05, robust=True, robust_min_n=20)
_BT_OK = {"n": 60, "exp_r": 0.30}


def test_gate_robust_cuts_decaying_edge():
    """+0.30 aggregate but the RECENT window is already negative -> observe."""
    obs, reason = guards.gate_decision(_BT_OK, False,
                                       sub_windows=[{"n": 30, "exp_r": 0.5},
                                                    {"n": 25, "exp_r": -0.2}], **_RW)
    assert obs and "recent OOS" in reason


def test_gate_robust_allows_emerging_alpha():
    """-0.23 old / +1.07 recent (RUNE break_retest): emerging alpha PASSES."""
    obs, reason = guards.gate_decision(_BT_OK, False,
                                       sub_windows=[{"n": 30, "exp_r": -0.23},
                                                    {"n": 22, "exp_r": 1.07}], **_RW)
    assert not obs and reason is None


def test_gate_robust_ignores_recent_window_with_small_n():
    """Negative recent window but not enough sample -> does not block."""
    obs, reason = guards.gate_decision(_BT_OK, False,
                                       sub_windows=[{"n": 30, "exp_r": 0.5},
                                                    {"n": 8, "exp_r": -0.9}], **_RW)
    assert not obs and reason is None


# ------------------- anti-beta exemption from the regime filter (06-29) -------------------
def test_regime_exempt_anti_beta_and_gold():
    from oscilion.strategies import portfolio as P
    assert P.regime_exempt("FLOW/USDT:USDT", "break_retest")      # anti-beta
    assert P.regime_exempt("PAXG/USDT:USDT", "ema_trend_stack")   # gold (per symbol)
    assert not P.regime_exempt("AVAX/USDT:USDT", "vwap_anchor")   # long beta -> filtered
    assert not P.regime_exempt("LINK/USDT:USDT", "orb_breakout")  # beta -> filtered


# ------------------------------ stale signal ------------------------------
def test_fresh_signal_passes_and_old_one_does_not():
    now = 1_900_000_000_000
    assert guards.is_fresh(now - 5 * 60_000, now, max_age_min=30)
    assert not guards.is_fresh(now - 31 * 60_000, now, max_age_min=30)


# ------------------------------ stop floor ------------------------------
def test_stop_pct_floor():
    assert guards.stop_pct_ok(0.01, min_stop_pct=0.002)      # 1% stop ok
    assert not guards.stop_pct_ok(0.0001, min_stop_pct=0.002)  # 0.01% stop -> 200x notional


# ------------------------- market regime (06-29) -------------------------
def test_regime_blocks_long_in_bear_and_short_in_bull():
    assert guards.market_regime_block("long", False) is not None    # bull trap
    assert guards.market_regime_block("short", True) is not None     # counter-trend short
    assert guards.market_regime_block("long", True) is None          # long in a bull market ok
    assert guards.market_regime_block("short", False) is None        # short in a bear market ok


def test_regime_exempt_and_unknown_do_not_block():
    assert guards.market_regime_block("long", False, exempt=True) is None     # uncorrelated gold
    assert guards.market_regime_block("long", None) is None                   # no data = fail-open
    assert guards.market_regime_block("long", False, enabled=False) is None   # filter off


# ------------------------- round-trip cost in R (06-29) -------------------------
def test_cost_toxic_tight_stops():
    from oscilion.backtest.costs import DEFAULT_COSTS
    assert DEFAULT_COSTS.round_trip_cost_r(0.0038) > 0.12     # XAU gold: ~0.24R -> blocked
    assert DEFAULT_COSTS.round_trip_cost_r(0.034) < 0.12      # wide AVAX stop: ~0.03R -> passes
    assert DEFAULT_COSTS.round_trip_cost_r(0.0) == math.inf   # stop 0 = infinite notional


# ------------------------------ symbol veto ------------------------------
class _St:
    def __init__(self, position):
        self.position = position


def test_symbol_veto_capital_blocks_observe_does_not():
    states = {
        ("TRX", "vwap_anchor"): _St({"side": "long", "observe": False}),
        ("TRX", "break_retest"): _St(None),
        ("BTC", "ema_trend_stack"): _St({"side": "long", "observe": True}),
    }
    assert guards.capital_position_on_symbol(states, "TRX") == "vwap_anchor"
    assert guards.capital_position_on_symbol(states, "BTC") is None   # observe does not block
    assert guards.capital_position_on_symbol(states, "DOT") is None


def test_symbol_veto_legacy_position_counts_as_capital():
    states = {("TRX", "orb_breakout"): _St({"side": "short"})}  # no observe flag
    assert guards.capital_position_on_symbol(states, "TRX") == "orb_breakout"


# ------------------------- portfolio limits (phase B) -------------------------
def _cluster_of(sym, strategy):
    return {"BTC": "majors", "BNB": "majors", "LINK": "majors", "DOT": "majors",
            "TRX": "trx"}.get(sym, sym)


def test_portfolio_max_concurrent_blocks():
    open_ = [("BTC", "ema"), ("LINK", "orb"), ("TRX", "orb")]
    r = guards.cluster_cap_reason(open_, "DOT", "orb", _cluster_of, 3, 2)
    assert r is not None and "max_concurrent" in r


def test_portfolio_max_per_cluster_blocks():
    open_ = [("BTC", "ema"), ("LINK", "orb")]          # 2 in 'majors'
    r = guards.cluster_cap_reason(open_, "DOT", "orb", _cluster_of, 3, 2)
    assert r is not None and "majors" in r
    # but TRX (another cluster) fits
    assert guards.cluster_cap_reason(open_, "TRX", "orb", _cluster_of, 3, 2) is None


def test_portfolio_with_room_passes():
    assert guards.cluster_cap_reason([("BTC", "ema")], "TRX", "orb", _cluster_of, 3, 2) is None
    assert guards.cluster_cap_reason([], "BTC", "ema", _cluster_of, 3, 2) is None


# ------------------------------ daily brake ------------------------------
def test_daily_brake_limit():
    cap = 10_000.0
    assert not guards.daily_loss_hit(-599.0, cap, max_daily_loss=0.06)
    assert guards.daily_loss_hit(-600.0, cap, max_daily_loss=0.06)   # exactly -6%
    assert guards.daily_loss_hit(-814.0, cap, max_daily_loss=0.06)   # the first cycle
    assert not guards.daily_loss_hit(+100.0, cap, max_daily_loss=0.06)


def test_utc_midnight():
    d = 86_400_000
    assert guards.utc_midnight_ms(5 * d + 123_456) == 5 * d
    assert guards.utc_midnight_ms(5 * d) == 5 * d


# ------------------------------ tp runner (no TP) ------------------------------
def test_tp_barrier_runner_never_fires():
    assert tp_barrier(None, "long") == math.inf
    assert tp_barrier(None, "short") == -math.inf
    assert tp_barrier(105.0, "long") == 105.0
    # no real candle exceeds +/-inf -> hit_tp is impossible
    assert not (1e17 >= tp_barrier(None, "long"))
    assert not (-1e17 <= tp_barrier(None, "short"))


def test_runner_strategies_return_tp_none():
    """tp_r=0 -> tp None (no 1e18 polluting sizing/logs)."""
    import numpy as np
    from oscilion.strategies import library as S
    n = 120
    a = lambda v: np.full(n, v, dtype=float)  # noqa: E731
    # context that fires an orb_breakout short: narrow prior range and a close below it
    close = a(100.0); close[-1] = 97.0
    low = a(99.5); high = a(100.5); high[-1] = 100.5; low[-1] = 96.5
    ema9 = a(100.0); ema21 = a(99.0)          # short: 9 > 21, NOT aligned down -> fresh ok
    tf = S.TFArrays(ts=np.arange(n) * 3_600_000 + 8 * 3_600_000, open=a(100), high=high,
                    low=low, close=close, volume=a(1), ema9=ema9, ema21=ema21,
                    ema50=a(100), atr=a(1.0), rsi=a(50), vwap=a(100))
    ctx = S.Ctx(sig=tf, sig_tf_h=1, aux={4: S.TFArrays(
        ts=np.arange(n) * 4 * 3_600_000, open=a(100), high=high, low=low, close=close,
        volume=a(1), ema9=a(100), ema21=a(100), ema50=a(200), atr=a(1), rsi=a(50), vwap=a(100))})
    out = S.orb_breakout(ctx, n - 1, {"tp_r": 0.0, "session_filter": False,
                                      "range_max_pct": 0.05, "fresh_gate": False})
    if out is not None:                        # if it fires, the runner has no TP
        assert out["tp"] is None
    # vwap_anchor with tp_r=0, direct path
    out2 = S.vwap_anchor(ctx, n - 1, {"tp_r": 0.0, "fresh_gate": False})
    if out2 is not None:
        assert out2["tp"] is None
