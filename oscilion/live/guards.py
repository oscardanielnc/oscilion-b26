"""Monitor process guards (FORWARD_REVIEW 2026-06-10, items 1, 2 and stale).

PURE functions (no network, no DB) so they are testable and reusable.
Philosophy: the edge lives in the strategies; these guards only stop trading what
is NOT validated, duplicated or stale. Every block leaves a trace (the caller logs
it); nothing is discarded silently.
"""
from __future__ import annotations

from config import config


def _ev(stats: dict | None) -> tuple[int, float | None]:
    """(n, exp_r), tolerant of None."""
    if not stats:
        return 0, None
    return int(stats.get("n") or 0), stats.get("exp_r")


def gate_decision(bt_stats: dict | None, observe_only: bool,
                  *, fw_stats: dict | None = None,
                  sub_windows: list[dict | None] | None = None,
                  min_n: int | None = None, min_exp_r: float | None = None,
                  fw_kill_n: int | None = None, fw_kill_exp_r: float | None = None,
                  fw_grad_n: int | None = None, fw_grad_exp_r: float | None = None,
                  robust: bool | None = None,
                  robust_min_n: int | None = None) -> tuple[bool, str | None]:
    """Decide whether a sym x strategy combo trades with capital.

    `bt_stats` = forward_results row with scope='backtest' (honest engine, OOS):
    local evidence, not research numbers the local history may not back up (the
    DOGE/vwap n=1 case from the first cycle).
    `fw_stats` = the REAL book (db.real_forward_stats: trades table, capital +
    observe, current rules era). Closes the missing loop (audit 06-29: observe beat
    capital because the gate never looked at the forward). Audit 07-02: it used to
    read the engine-SIMULATED 'forward' scope, which diverged from the real book.

    Priority: the real forward (kill/graduation) OVERRIDES the backtest, because it
    measures how the combo trades TODAY. Without enough forward sample, the
    backtest decides.

    Returns (observe, reason): observe=True -> virtual trade WITHOUT capital.
    """
    min_n = config.gate_min_n if min_n is None else min_n
    min_exp_r = config.gate_min_exp_r if min_exp_r is None else min_exp_r
    fw_kill_n = config.gate_fw_kill_n if fw_kill_n is None else fw_kill_n
    fw_kill_exp_r = config.gate_fw_kill_exp_r if fw_kill_exp_r is None else fw_kill_exp_r
    fw_grad_n = config.gate_fw_grad_n if fw_grad_n is None else fw_grad_n
    fw_grad_exp_r = config.gate_fw_grad_exp_r if fw_grad_exp_r is None else fw_grad_exp_r
    robust = config.gate_robust if robust is None else robust
    robust_min_n = config.gate_robust_min_n if robust_min_n is None else robust_min_n

    fw_n, fw_exp = _ev(fw_stats)

    if observe_only:
        # GRADUATION: the real forward confirms edge with margin -> promote to capital.
        if fw_n >= fw_grad_n and fw_exp is not None and fw_exp >= fw_grad_exp_r:
            return False, None
        return True, "observe_only (assignment)"

    # KILL-SWITCH: the real forward already proved the combo bleeds -> cut capital.
    if fw_n >= fw_kill_n and fw_exp is not None and fw_exp <= fw_kill_exp_r:
        return True, f"forward kill: exp_R={fw_exp:+.3f} (n={fw_n}) <= {fw_kill_exp_r:+.2f}"

    # Backtest (OOS) gate: the base filter while the forward is not yet decisive.
    if not bt_stats:
        return True, "gate: no local backtest (forward_results empty)"
    n, exp_r = _ev(bt_stats)
    if n < min_n:
        return True, f"gate: n={n} < {min_n}"
    if exp_r is None or exp_r <= min_exp_r:
        er = "-" if exp_r is None else f"{exp_r:+.3f}"
        return True, f"gate: exp_R={er} <= {min_exp_r:+.2f}"
    # RECENCY-AWARE robustness: the MOST RECENT OOS window (sub_windows[-1]) must not
    # be decaying. Blocks the dangerous case (+0.30 old / -0.20 recent = an edge that
    # is fading) BUT allows EMERGING, regime-specific alpha (-0.20 old / +1.07 recent),
    # which was the working thesis (break_retest wins when alts fall, a recent
    # phenomenon). Averaging both or requiring both positive would kill it.
    if robust and sub_windows:
        wn, wexp = _ev(sub_windows[-1])
        if wn >= robust_min_n and (wexp is None or wexp <= min_exp_r):
            we = "-" if wexp is None else f"{wexp:+.3f}"
            return True, f"robust gate: recent OOS exp_R={we} <= {min_exp_r:+.2f} (n={wn}), edge decaying"
    return False, None


def market_regime_block(side: str, market_bull: bool | None, *,
                        enabled: bool = True, exempt: bool = False) -> str | None:
    """Regime beta filter: do not trade while the base market runs AGAINST the
    trade's side. A continuation long in a bear market = bull trap (the 17 vwap
    entries of audit 06-29); a short in a bull market, symmetric. Returns the block
    reason, or None if the entry is allowed.

    `market_bull` None => unknown regime (no data) -> does not block (fail-open).
    `exempt` True => asset uncorrelated with the benchmark (gold) -> not applied.
    """
    if not enabled or exempt or market_bull is None:
        return None
    if side == "long" and not market_bull:
        return "bear market (benchmark<EMA) against LONG"
    if side == "short" and market_bull:
        return "bull market (benchmark>EMA) against SHORT"
    return None


def is_fresh(sig_close_ms: int, now_ms: int, max_age_min: int | None = None) -> bool:
    """True if the signal candle closed recently. An old signal (downtime, failed
    refresh) would enter at a stale reference price, and it can bypass session
    filters evaluated with the CANDLE's time rather than the current time."""
    max_age = (config.max_signal_age_min if max_age_min is None else max_age_min) * 60_000
    return (now_ms - sig_close_ms) <= max_age


def stop_pct_ok(stop_pct: float, min_stop_pct: float | None = None) -> bool:
    """Stop-distance floor: fixed risk / stop->0 = absurd notional."""
    floor = config.min_stop_pct if min_stop_pct is None else min_stop_pct
    return stop_pct >= floor


def cluster_cap_reason(open_combos: list[tuple[str, str]], new_sym: str, new_strategy: str,
                       cluster_of, max_concurrent: int, max_per_cluster: int) -> str | None:
    """Portfolio limits from phase B (tuned.py): the scheme the portfolio was
    VALIDATED with. Without them, live could carry 7 x 2% = 14% of simultaneous
    risk in a ~0.7-correlated cluster.

    `open_combos` = [(sym, strategy)] of open positions WITH CAPITAL.
    Returns the block reason, or None if it fits.
    """
    if len(open_combos) >= max_concurrent:
        return f"max_concurrent {len(open_combos)}/{max_concurrent}"
    cl = cluster_of(new_sym, new_strategy)
    n_cl = sum(1 for s, strat in open_combos if cluster_of(s, strat) == cl)
    if n_cl >= max_per_cluster:
        return f"cluster '{cl}' {n_cl}/{max_per_cluster}"
    return None


def utc_midnight_ms(now_ms: int) -> int:
    """00:00 UTC of the day of `now_ms`: the daily brake resets with the UTC day."""
    return (now_ms // 86_400_000) * 86_400_000


def daily_loss_hit(pnl_today: float, capital: float,
                   max_daily_loss: float | None = None) -> bool:
    """True if today's closed PnL already burned the daily limit (-6% by default).
    Only blocks new capital entries; open positions keep being managed."""
    lim = config.max_daily_loss if max_daily_loss is None else max_daily_loss
    return pnl_today <= -lim * capital


def capital_position_on_symbol(states: dict, sym: str) -> str | None:
    """Strategy holding an open position WITH CAPITAL on `sym` (or None).

    Cross veto: one capital position per symbol, any direction. Same direction
    doubles the bet; opposite direction pays double cost to end up flat. Observe
    positions do not block (no capital). Legacy positions without the `observe`
    flag count as capital (conservative).
    """
    for (s, strat), st in states.items():
        pos = getattr(st, "position", None)
        if s == sym and pos is not None and not pos.get("observe", False):
            return strat
    return None
