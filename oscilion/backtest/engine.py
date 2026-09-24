"""Walk-forward backtest engine for the range-reversion signal, WITHOUT look-ahead.

Honesty rules:
  - The signal on bar i uses ONLY data <= the close of i (rolling window).
  - The entry fills at the OPEN of bar i+1 (decide at the close, fill after).
    Future information is never used.
  - Conservative intrabar handling: if stop and TP are both touched in the same
    candle, the STOP is assumed to have fired first (worst case).
  - Real costs: maker/taker fees, taker slippage and funding every 8h.
  - Risk-based sizing: each trade risks `risk` of current equity => loss at the
    stop = risk * equity (the 2% invariant).

Reuses the SAME signal logic as live (`analysis.candidate_from_df`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from config import config
from oscilion.analysis import breakout_candidate, candidate_from_df
from oscilion.backtest.costs import DEFAULT_COSTS, CostModel
from oscilion.data import store
from oscilion.signals.entry import confirm_turn

log = logging.getLogger(__name__)


@dataclass
class BTParams:
    capital: float = 10_000.0
    risk: float = config.risk_per_trade
    min_rr: float = config.min_rr
    min_score: float = 0.0           # optional conviction gate
    lookback: int = 96               # range window (same as live)
    warmup: int = 320                # bars for indicator convergence
    max_hold_bars: int = 72          # position timeout
    allow_regimes: tuple[str, ...] = ("range", "trend")  # never 'chaos'
    require_confirmation: bool = False  # require turn confirmation
    strategy: str = "reversion"         # reversion | momentum (probe)
    min_breakout_atr: float = 0.0       # momentum: minimum breakout in ATR
    costs: CostModel = field(default_factory=lambda: DEFAULT_COSTS)


def _funding_between(funding: pd.DataFrame, t0: int, t1: int) -> list[float]:
    if funding.empty:
        return []
    m = (funding["ts"] > t0) & (funding["ts"] <= t1)
    return funding.loc[m, "funding_rate"].tolist()


def backtest_symbol(sym: str, tf: str | None = None, p: BTParams | None = None) -> list[dict]:
    """Simulate the symbol bar by bar. Returns the list of closed trades."""
    p = p or BTParams()
    tf = tf or config.base_timeframe
    df = store.load_bars(sym, tf).reset_index(drop=True)
    funding = store.load_funding(sym)
    n = len(df)
    if n < p.warmup + 5:
        log.warning("%s %s: not enough history (%d bars)", sym, tf, n)
        return []

    ts = df["ts"].to_numpy()
    o, h, l, c = (df[x].to_numpy() for x in ("open", "high", "low", "close"))

    equity = p.capital
    trades: list[dict] = []
    pos: dict | None = None
    pending: dict | None = None

    for i in range(p.warmup, n):
        # 1) fill the pending entry at this bar's OPEN
        if pending is not None and pos is None:
            entry_px = p.costs.fill_price(o[i], pending["side"], is_entry=True, maker=False)
            risk_amt = equity * p.risk
            stop_pct = abs(entry_px - pending["stop"]) / entry_px
            if stop_pct <= 0:
                pending = None
            else:
                notional = risk_amt / stop_pct
                pos = {**pending, "sym": sym, "entry": entry_px, "entry_i": i, "entry_ts": int(ts[i]),
                       "notional": notional, "stop_pct": stop_pct,
                       "equity_before": equity, "mae": 0.0, "mfe": 0.0,
                       "entry_fee": p.costs.fee(notional, maker=False)}
                pending = None

        # 2) manage the open position with this bar's range
        if pos is not None:
            side, entry = pos["side"], pos["entry"]
            if side == "long":
                pos["mfe"] = max(pos["mfe"], (h[i] - entry) / entry)
                pos["mae"] = max(pos["mae"], (entry - l[i]) / entry)
                hit_stop, hit_tp = l[i] <= pos["stop"], h[i] >= pos["tp"]
            else:
                pos["mfe"] = max(pos["mfe"], (entry - l[i]) / entry)
                pos["mae"] = max(pos["mae"], (h[i] - entry) / entry)
                hit_stop, hit_tp = h[i] >= pos["stop"], l[i] <= pos["tp"]

            exit_px = exit_reason = None
            maker = False
            if hit_stop:                                   # worst case first
                exit_px = p.costs.fill_price(pos["stop"], side, is_entry=False, maker=False)
                exit_reason = "stop"
            elif hit_tp:
                exit_px = p.costs.fill_price(pos["tp"], side, is_entry=False, maker=True)
                exit_reason, maker = "tp", True
            elif i - pos["entry_i"] >= p.max_hold_bars:
                exit_px = p.costs.fill_price(c[i], side, is_entry=False, maker=False)
                exit_reason = "timeout"

            if exit_px is not None:
                trades.append(_close(pos, exit_px, int(ts[i]), i, exit_reason, maker, funding, p))
                equity = pos["equity_before"] + trades[-1]["pnl"]
                pos = None

        # 3) if flat, evaluate the signal on the window up to i (close)
        if pos is None and pending is None and i + 1 < n:
            window = df.iloc[i - p.warmup + 1: i + 1]
            if p.strategy == "momentum":
                cand = breakout_candidate(sym, window, tf=tf, lookback=p.lookback)
            else:
                cand = candidate_from_df(sym, window, tf=tf, lookback=p.lookback)
            ok = (cand.get("tradeable") and cand.get("score", 0) >= p.min_score
                  and cand.get("regime") in p.allow_regimes)
            if ok and p.strategy == "momentum" and p.min_breakout_atr > 0:
                ok = cand.get("components", {}).get("breakout_atr", 0.0) >= p.min_breakout_atr
            if ok and p.require_confirmation:
                edge = cand.get("lo") if cand["side"] == "long" else cand.get("hi")
                ok = confirm_turn(window, cand["side"], edge=edge)[0]
            if ok:
                pending = {"side": cand["side"], "stop": cand["stop"], "tp": cand["tp"],
                           "score": cand["score"], "regime": cand["regime"],
                           "vol_regime": cand.get("vol_regime"),
                           "rr_planned": cand["rr"], "leverage": cand["leverage"]}

    return trades


def _close(pos: dict, exit_px: float, exit_ts: int, exit_i: int,
           reason: str, maker: bool, funding: pd.DataFrame, p: BTParams) -> dict:
    side, entry, notional = pos["side"], pos["entry"], pos["notional"]
    price_ret = (exit_px - entry) / entry if side == "long" else (entry - exit_px) / entry
    gross = price_ret * notional
    exit_fee = p.costs.fee(notional, maker=maker)
    fees = pos["entry_fee"] + exit_fee
    fund = sum(p.costs.funding(notional, side, r)
               for r in _funding_between(funding, pos["entry_ts"], exit_ts))
    pnl = gross - fees - fund
    eq_before = pos["equity_before"]
    risk_dist = abs(entry - pos["stop"])
    rr_realized = (price_ret * entry) / risk_dist if risk_dist > 0 else 0.0
    return {
        "sym": pos["sym"], "side": side, "regime": pos["regime"],
        "vol_regime": pos.get("vol_regime"), "score": pos["score"],
        "entry_ts": pos["entry_ts"], "exit_ts": exit_ts, "bars_held": exit_i - pos["entry_i"],
        "entry": entry, "exit": exit_px, "stop": pos["stop"], "tp": pos["tp"],
        "notional": notional, "leverage": pos["leverage"], "exit_reason": reason,
        "gross": gross, "fees": fees, "funding": fund, "pnl": pnl,
        "ret": pnl / eq_before if eq_before > 0 else 0.0,
        "rr_realized": rr_realized, "mae": pos["mae"], "mfe": pos["mfe"],
    }


def run(symbols: list[str] | None = None, tf: str | None = None,
        p: BTParams | None = None) -> dict:
    """Backtest several symbols. Returns trades per symbol + the global pool."""
    p = p or BTParams()
    symbols = symbols or config.symbols
    tf = tf or config.base_timeframe
    per_symbol: dict[str, list[dict]] = {}
    pooled: list[dict] = []
    for s in symbols:
        t = backtest_symbol(s, tf, p)
        per_symbol[s] = t
        pooled.extend(t)
        log.info("backtest %s %s: %d trades", s, tf, len(t))
    pooled.sort(key=lambda x: x["exit_ts"])
    return {"per_symbol": per_symbol, "pooled": pooled, "params": p, "tf": tf}
