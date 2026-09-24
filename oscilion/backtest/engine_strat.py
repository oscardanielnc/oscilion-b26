"""Honest engine for the directional strategies in strategies/library.py.

- Signal on a coarse TF (2h/4h) resampled from 1h; NO look-ahead.
- Exit resolved on a FINE TF (15m by default) with a PESSIMISTIC tie-break
  (stop before TP inside the same fine candle).
- Entry at the open of the first fine candle after the signal close (T).
- Real costs (taker/maker fees, slippage, 8h funding).
- Primary per-trade metric in **R** (pnl / risk budget), independent of equity
  compounding. Results are kept PER SYMBOL (never blindly averaged).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from config import config
from oscilion.backtest.costs import DEFAULT_COSTS, CostModel
from oscilion.data import store
from oscilion.features import market_regime
from oscilion.strategies import library as S
from oscilion.strategies.context import build_ctx

log = logging.getLogger(__name__)
_H = 3_600_000


@dataclass
class StratParams:
    strategy: str = "momentum_pullback"
    risk: float = 0.02
    exit_tf: str = "15m"
    max_hold_signal_bars: int = 60        # timeout in signal bars
    costs: CostModel = field(default_factory=lambda: DEFAULT_COSTS)
    maker_entry: bool = False
    exit_mode: str = "fixed_tp"           # fixed_tp | trailing (R5)
    trail_atr: float = 2.0                # trailing distance in signal-TF ATR
    be_at_r: float = 1.0                  # move to break-even at +be_at_r R
    # time-stop (R6): after `time_stop_h` hours, exit at market UNLESS the trade is
    # winning >= `time_stop_keep_r` R (let winners run, lesson #9).
    # 0 = disabled. A huge keep_r = hard time-stop (always cuts).
    time_stop_h: float = 0.0
    time_stop_keep_r: float = 1e9
    params: dict = field(default_factory=dict)
    # Structural filters (audit 06-29). They mirror the live monitor so that
    # forward_results (read by the gate) reflects how trading really happens:
    #   - cost_filter: rejects cost-toxic entries (round-trip cost > max_cost_r).
    #   - regime_close_ts/regime_bull: if non-empty, applies the market regime gate
    #     (no LONG in a bear market / SHORT in a bull market). Empty = no filter (gold).
    cost_filter: bool = True
    regime_close_ts: np.ndarray = field(default_factory=lambda: np.array([]))
    regime_bull: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))


@dataclass
class CoinBundle:
    """Preloaded data for one symbol + strategy (expensive to build, reusable
    across parameter sweeps)."""
    sym: str
    ctx: S.Ctx
    ets: np.ndarray
    eo: np.ndarray
    eh: np.ndarray
    el: np.ndarray
    ec: np.ndarray
    fund_ts: np.ndarray
    fund_rate: np.ndarray


def load_bundle(sym: str, strategy: str, exit_tf: str = "15m") -> CoinBundle | None:
    ctx = build_ctx(sym, strategy)
    if ctx is None:
        return None
    exit_df = store.load_bars(sym, exit_tf)
    if exit_df.empty:
        return None
    funding = store.load_funding(sym)
    return CoinBundle(
        sym=sym, ctx=ctx,
        ets=exit_df["ts"].to_numpy(),
        eo=exit_df["open"].to_numpy(), eh=exit_df["high"].to_numpy(),
        el=exit_df["low"].to_numpy(), ec=exit_df["close"].to_numpy(),
        fund_ts=funding["ts"].to_numpy() if not funding.empty else np.array([]),
        fund_rate=funding["funding_rate"].to_numpy() if not funding.empty else np.array([]),
    )


def run(bundle: CoinBundle, p: StratParams) -> list[dict]:
    spec = S.REGISTRY[p.strategy]
    fn = spec["fn"]
    ctx = bundle.ctx
    sym = bundle.sym
    ets, eo, eh, el, ec = bundle.ets, bundle.eo, bundle.eh, bundle.el, bundle.ec
    fund_ts, fund_rate = bundle.fund_ts, bundle.fund_rate
    n_exit = len(ets)
    sig_tf_ms = ctx.sig_tf_h * _H
    max_hold_ms = p.max_hold_signal_bars * sig_tf_ms

    equity = 10_000.0
    trades: list[dict] = []
    busy_until_ts = -1                       # no new signal while a position is open
    sig = ctx.sig
    for i in range(len(sig.ts)):
        T = int(sig.ts[i]) + sig_tf_ms       # signal close
        if T <= busy_until_ts:
            continue
        cand = fn(ctx, i, p.params)
        if cand is None:
            continue

        # MARKET REGIME gate (same as the live monitor): skip the trade when the
        # benchmark runs against its side. Empty = no filter (gold is exempt).
        if p.regime_close_ts.size:
            bull = market_regime.bull_at(p.regime_close_ts, p.regime_bull, T)
            if bull is not None and ((cand["side"] == "long" and not bull)
                                     or (cand["side"] == "short" and bull)):
                continue

        # entry: first fine candle with open_ts >= T
        ei = int(np.searchsorted(ets, T, side="left"))
        if ei >= n_exit:
            break
        side = cand["side"]
        maker = p.maker_entry
        entry_px = p.costs.fill_price(eo[ei], side, is_entry=True, maker=maker)
        stop, tp = cand["stop"], cand["tp"]            # tp=None = runner (no TP)
        tp_lvl = S.tp_barrier(tp, side)                # +/-inf for a runner: never fires
        # re-validate the geometry with the real fill
        risk_dist = (entry_px - stop) if side == "long" else (stop - entry_px)
        if risk_dist <= 0:
            continue
        # stop floor (same as the monitor): fixed risk / stop->0 blows up the notional
        stop_pct = risk_dist / entry_px
        if stop_pct < config.min_stop_pct:
            continue
        # cost filter (same as the monitor): tight stop => big notional => fees eat R
        if p.cost_filter and p.costs.round_trip_cost_r(stop_pct) > config.max_cost_r:
            continue
        risk_amt = equity * p.risk
        notional = risk_amt / (risk_dist / entry_px)
        entry_fee = p.costs.fee(notional, maker=maker)
        atr_sig = float(sig.atr[i]) if np.isfinite(sig.atr[i]) else risk_dist

        # walk fine candles until exit (pessimistic: stop before TP) or timeout
        exit_px = exit_reason = None
        k = ei
        deadline = T + max_hold_ms
        ts_on = p.time_stop_h > 0
        ts_ms = p.time_stop_h * _H

        def _time_stop(kk: int):
            """On time-stop, exit at the close unless the trade is winning >= keep_r."""
            if not ts_on or (ets[kk] - T) < ts_ms:
                return None
            ur = ((ec[kk] - entry_px) if side == "long" else (entry_px - ec[kk])) / risk_dist
            return None if ur >= p.time_stop_keep_r else (float(ec[kk]), "time")

        if p.exit_mode == "trailing":
            trail_d = p.trail_atr * atr_sig
            be_move = p.be_at_r * risk_dist
            cur_stop = stop
            best = entry_px
            while k < n_exit and ets[k] <= deadline:
                hi, lo = eh[k], el[k]
                # 1) check the stop at the level set by previous bars (pessimistic)
                if (side == "long" and lo <= cur_stop) or (side == "short" and hi >= cur_stop):
                    exit_px, exit_reason = cur_stop, "trail"; break
                ts = _time_stop(k)
                if ts:
                    exit_px, exit_reason = ts; break
                # 2) update the best price and ratchet the stop
                if side == "long":
                    best = max(best, hi)
                    if best - entry_px >= be_move:
                        cur_stop = max(cur_stop, entry_px)
                    cur_stop = max(cur_stop, best - trail_d)
                else:
                    best = min(best, lo)
                    if entry_px - best >= be_move:
                        cur_stop = min(cur_stop, entry_px)
                    cur_stop = min(cur_stop, best + trail_d)
                k += 1
        else:
            while k < n_exit and ets[k] <= deadline:
                hi, lo = eh[k], el[k]
                if side == "long":
                    hit_stop, hit_tp = lo <= stop, hi >= tp_lvl
                else:
                    hit_stop, hit_tp = hi >= stop, lo <= tp_lvl
                if hit_stop:
                    exit_px, exit_reason = stop, "stop"; break
                ts = _time_stop(k)
                if ts:
                    exit_px, exit_reason = ts; break
                if hit_tp:
                    exit_px, exit_reason = tp_lvl, "tp"; break
                k += 1
        if exit_px is None:                  # timeout or end of data
            k = min(k, n_exit - 1)
            exit_px, exit_reason = float(ec[k]), "timeout"
        exit_ts = int(ets[k])

        taker_exit = exit_reason in ("stop", "timeout", "trail", "time")
        fund = 0.0
        if fund_ts.size:
            m = (fund_ts > T) & (fund_ts <= exit_ts)
            if m.any():
                fund = float(np.sum([p.costs.funding(notional, side, r) for r in fund_rate[m]]))
        pnl, exit_fill = p.costs.realized(side, entry_px, exit_px, notional, entry_fee,
                                          maker_exit=not taker_exit, funding_total=fund)
        R = pnl / risk_amt if risk_amt > 0 else 0.0
        trades.append({
            "sym": sym, "strategy": p.strategy, "side": side,
            "entry_ts": T, "exit_ts": exit_ts, "entry": entry_px, "exit": exit_fill,
            "stop": stop, "tp": tp, "exit_reason": exit_reason,
            "pnl": pnl, "ret": pnl / equity if equity > 0 else 0.0, "R": R,
            "hold_h": (exit_ts - T) / _H,
        })
        equity += pnl
        busy_until_ts = exit_ts              # one position at a time
    return trades


def backtest_symbol_strat(sym: str, p: StratParams) -> list[dict]:
    """Convenience: load the bundle and run it."""
    bundle = load_bundle(sym, p.strategy, p.exit_tf)
    if bundle is None:
        return []
    return run(bundle, p)
