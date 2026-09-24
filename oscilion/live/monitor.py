"""Live monitor, dry-run: it recommends and records, it never places orders.

For each (coin, strategy) in the portfolio:
  - detects when a new CLOSED signal candle fires the strategy -> ENTER alert +
    records the decision (virtual trade opened in memory);
  - manages the virtual trade on closed 15m candles (stop/TP, pessimistic) ->
    EXIT/TAKE_PROFIT alert + records the closed trade (with strategy and R) in the DB;
  - periodically refreshes the forward validation snapshot (backtest vs live).

The authoritative validation METRICS come from `live.forward` (honest engine,
single source of truth). The monitor provides the real-time alerts and the feed.
It reuses the same signal logic as the backtest (no divergence).
"""
from __future__ import annotations

import logging
import time

import numpy as np

from config import config
from oscilion.backtest.costs import DEFAULT_COSTS
from oscilion.data import fetch, store
from oscilion.features import market_regime
from oscilion.live import forward, guards
from oscilion.notify import notify
from oscilion.persistence import db
from oscilion.strategies import all_assignments, library as S, portfolio as P
from oscilion.strategies.context import build_ctx

log = logging.getLogger(__name__)
_H = 3_600_000


class _PosState:
    __slots__ = ("position", "last_sig_ts", "last_15m_ts")

    def __init__(self):
        self.position = None       # dict | None
        self.last_sig_ts = 0       # last processed signal close
        self.last_15m_ts = 0       # last 15m candle processed for management

    def to_dict(self) -> dict:
        return {"position": self.position, "last_sig_ts": self.last_sig_ts,
                "last_15m_ts": self.last_15m_ts}

    @classmethod
    def from_dict(cls, d: dict) -> "_PosState":
        st = cls()
        st.position = d.get("position")
        st.last_sig_ts = int(d.get("last_sig_ts", 0) or 0)
        st.last_15m_ts = int(d.get("last_15m_ts", 0) or 0)
        return st


class LiveMonitor:
    def __init__(self, *, refresh_data: bool = True, capital: float = 10_000.0,
                 forward_every_ticks: int = 240, snapshot_every_ticks: int = 60,
                 funding_every_ticks: int = 480):
        self.refresh_data = refresh_data
        self.capital = capital
        self.forward_every_ticks = forward_every_ticks
        self.snapshot_every_ticks = snapshot_every_ticks    # ~hourly
        self.funding_every_ticks = funding_every_ticks      # ~8h (funding settlement)
        self.assignments = all_assignments()
        self.symbols = sorted({s for s, _a in self.assignments})
        self._ticks = 0
        self._daily_halt_notified = None    # UTC day already notified of the daily brake
        self._mkt_tick = -1                 # per-tick market regime cache
        self._mkt_bull = None
        # Rehydrate persisted state (survives restarts -> forward test without holes).
        db.init_db()
        saved = db.load_monitor_states()
        self.states = {}
        rehydrated = 0
        for s, a in self.assignments:
            k = self._key(s, a.strategy)
            if k in saved:
                stt = _PosState.from_dict(saved[k])
                # Drop positions from an older format (missing the current execution
                # fields) so closing them does not break after an upgrade.
                if stt.position and "notional" not in stt.position:
                    stt.position = None
                self.states[(s, a.strategy)] = stt
                rehydrated += 1
            else:
                self.states[(s, a.strategy)] = _PosState()
        if rehydrated:
            log.info("monitor: %d series rehydrated from the DB", rehydrated)

    @staticmethod
    def _key(sym: str, strategy: str) -> str:
        return f"{sym}|{strategy}"

    # ------------------------------ data -------------------------------
    def _refresh(self, sym: str) -> None:
        # Recent candles only (history is already seeded); light on the network.
        for tf in ("1h", "15m"):
            tf_ms = fetch.timeframe_to_ms(tf)
            since = fetch._now_ms() - 250 * tf_ms
            df = fetch.fetch_ohlcv(sym, tf, since=since)
            if not df.empty:
                store.save_bars(sym, tf, df)

    def _refresh_funding(self, sym: str) -> None:
        # Funding settles every 8h. The per-tick _refresh (OHLCV) did not touch it,
        # so the parquet froze at the last sync_all and live trades closed with
        # fund=0 (audit 06-29). It is refreshed on its own cadence.
        since = fetch._now_ms() - 10 * 86_400_000
        f = fetch.fetch_funding(sym, since=since)
        if not f.empty:
            store.save_funding(sym, f)

    def _market_bull(self) -> bool | None:
        """Benchmark (BTC) regime: True bullish (close > EMA on a higher TF), False
        bearish, None if there is no data. Cached per tick (N entries query it)."""
        if self._mkt_tick == self._ticks:
            return self._mkt_bull
        self._mkt_tick = self._ticks
        self._mkt_bull = None
        try:
            bars = store.load_bars(config.market_benchmark, "1h")
            self._mkt_bull = market_regime.latest_bull(
                bars, config.market_regime_tf_h, config.market_regime_ema)
        except Exception:
            log.exception("market regime %s", config.market_benchmark)
        return self._mkt_bull

    # ------------------------------ tick -------------------------------
    def step(self) -> list[dict]:
        self._ticks += 1
        alerts: list[dict] = []
        if self.refresh_data:
            for sym in self.symbols:
                try:
                    self._refresh(sym)
                except Exception:
                    log.exception("refresh %s", sym)

        # Forward BEFORE evaluating signals: the validation gate reads
        # forward_results, so the first tick already decides with fresh data.
        if self.forward_every_ticks and self._ticks % self.forward_every_ticks == 1:
            try:
                forward.refresh()
            except Exception:
                log.exception("forward refresh")

        # Funding on a ~8h cadence keeps the parquet current so closing trades
        # deducts the real funding instead of assuming 0.
        if self.refresh_data and self.funding_every_ticks and \
                self._ticks % self.funding_every_ticks == 1:
            for sym in self.symbols:
                try:
                    self._refresh_funding(sym)
                except Exception:
                    log.exception("refresh funding %s", sym)

        for sym, a in self.assignments:
            try:
                alerts.extend(self._step_one(sym, a))
            except Exception:
                log.exception("monitor %s %s", sym, a.strategy)
                db.log_event("ERROR", "live.monitor", f"{sym} {a.strategy} failed in tick")
            else:
                # Persist ONLY after a successful step: if _step_one blew up halfway,
                # the in-memory state may be corrupt and a restart would rehydrate a
                # broken position (double close / phantom re-entry).
                db.save_monitor_state(self._key(sym, a.strategy),
                                      self.states[(sym, a.strategy)].to_dict())

        # Concise observer snapshot: on a cadence (~hourly) or on every change (an
        # entry/exit alert) -> an auditable trace even when nothing trades.
        cadence = self.snapshot_every_ticks and self._ticks % self.snapshot_every_ticks == 1
        if cadence or alerts:
            try:
                self._persist_snapshots()
            except Exception:
                log.exception("persist snapshots")
        return alerts

    def _persist_snapshots(self) -> None:
        from oscilion.live.signals import live_signals
        for s in live_signals():
            db.log_series_snapshot(
                s["sym"], s["strategy"], state=s["state"], direction=s["direction"],
                price=s["price"], checklist_ok=s["checklist_ok"],
                checklist_total=s["checklist_total"], signal_active=s["signal_active"],
                in_trade=s["in_trade"],
            )

    def _step_one(self, sym: str, a) -> list[dict]:
        st = self.states[(sym, a.strategy)]
        ctx = build_ctx(sym, a.strategy, tail_1h=1500)
        if ctx is None:
            return []
        i = len(ctx.sig.ts) - 1
        if i < 1:
            return []
        sig_ms = ctx.sig_tf_h * _H
        alerts: list[dict] = []

        # 1) manage the open position on new 15m candles
        if st.position is not None:
            ex = self._manage(sym, st)
            if ex:
                alerts.append(ex)

        # 2) evaluate a new closed signal candle
        sig_close = int(ctx.sig.ts[i]) + sig_ms
        if sig_close > st.last_sig_ts:
            st.last_sig_ts = sig_close
            if st.position is None:
                cand = S.REGISTRY[a.strategy]["fn"](ctx, i, a.params)
                if cand:
                    # Stale signal: after downtime or a failed refresh the candle is
                    # old -> stale reference price and session filters no longer hold.
                    if not guards.is_fresh(sig_close, int(time.time() * 1000)):
                        age_min = (int(time.time() * 1000) - sig_close) // 60_000
                        db.log_event("WARN", "live.monitor",
                                     f"{sym} {a.strategy}: stale signal ({age_min}m > "
                                     f"{config.max_signal_age_min}m), not entering")
                        return alerts
                    r = self._open(sym, a, cand, sig_close)
                    if r:
                        alerts.append(r)
        return alerts

    def _open(self, sym: str, a, cand: dict, sig_close: int) -> dict | None:
        # SAME method as the engine (forward): taker entry + slippage, risk sizing,
        # entry fee -> the monitor's trades match the validation.
        side = cand["side"]
        entry = DEFAULT_COSTS.fill_price(float(cand["entry_ref"]), side, is_entry=True, maker=False)
        stop = float(cand["stop"])
        tp = float(cand["tp"]) if cand.get("tp") is not None else None   # None = runner
        risk_dist = (entry - stop) if side == "long" else (stop - entry)
        if risk_dist <= 0:
            return None
        stop_pct = risk_dist / entry
        if not guards.stop_pct_ok(stop_pct):
            db.log_event("WARN", "live.monitor",
                         f"{sym} {a.strategy}: stop_pct {stop_pct:.4%} < floor "
                         f"{config.min_stop_pct:.2%}, not opening (absurd notional)")
            return None

        # COST filter (audit 06-29): a very tight stop inflates the notional and fees
        # eat the R (gold/TRX). If the estimated round-trip cost exceeds the cap, the
        # trade cannot pay for its edge -> rejected (capital and observe alike).
        cost_r = DEFAULT_COSTS.round_trip_cost_r(stop_pct)
        if cost_r > config.max_cost_r:
            db.log_event("WARN", "live.monitor",
                         f"{sym} {a.strategy}: cost {cost_r:.1%} of R > cap "
                         f"{config.max_cost_r:.0%} (stop {stop_pct:.2%} too tight), not opening")
            db.log_decision(sym, "no-trade", f"cost-toxic: {cost_r:.1%} of R (stop {stop_pct:.2%})")
            return None

        # MARKET REGIME filter (audit 06-29): do not trade while the base market runs
        # against the trade's side (gold exempt). Blocks the bull traps that cost
        # -11R in vwap_anchor.
        exempt = P.regime_exempt(sym, a.strategy)
        regime_block = guards.market_regime_block(
            side, self._market_bull(), enabled=config.market_regime_filter, exempt=exempt)
        if regime_block is not None:
            db.log_event("INFO", "live.monitor",
                         f"{sym} {a.strategy}: regime, {regime_block}, not opening")
            db.log_decision(sym, "no-trade", f"market regime: {regime_block}")
            return None

        # Validation gate (FORWARD_REVIEW #1): without enough local evidence (n, exp_R
        # from the honest engine) the trade is demoted to observe (no capital).
        # fw_stats = the REAL book of the current era (audit 07-02): the simulated
        # 'forward' scope is for the dashboard, not for deciding capital.
        observe, gate_reason = guards.gate_decision(
            db.get_forward_backtest(sym, a.strategy), a.observe_only,
            fw_stats=db.real_forward_stats(sym, a.strategy),
            sub_windows=[db.get_forward_result(sym, a.strategy, "oos_a"),
                         db.get_forward_result(sym, a.strategy, "oos_b")])
        if observe and not a.observe_only:
            db.log_event("WARN", "live.monitor",
                         f"{sym} {a.strategy}: demoted to observe, {gate_reason}")
        elif not observe and a.observe_only:
            db.log_event("INFO", "live.monitor",
                         f"{sym} {a.strategy}: GRADUATED to capital by forward, the real edge confirms")

        # Portfolio guards: only for trades WITH capital (observe is stats-only).
        if not observe:
            # Cross veto (FORWARD_REVIEW #2): one position WITH CAPITAL per symbol.
            other = guards.capital_position_on_symbol(self.states, sym)
            if other is not None:
                db.log_event("INFO", "live.monitor",
                             f"{sym} {a.strategy}: symbol veto, capital already open in {other}")
                db.log_decision(sym, "no-trade", f"symbol veto: open position ({other})")
                return None
            # Phase B limits (the scheme the portfolio was validated with): max
            # concurrent capital positions and max per correlation cluster.
            open_caps = [(s, strat) for (s, strat), st2 in self.states.items()
                         if st2.position is not None and not st2.position.get("observe", False)]
            cap_reason = guards.cluster_cap_reason(open_caps, sym, a.strategy,
                                                   P.cluster_of, P.MAX_CONCURRENT, P.MAX_PER_CLUSTER)
            if cap_reason is not None:
                db.log_event("INFO", "live.monitor",
                             f"{sym} {a.strategy}: portfolio limit, {cap_reason}")
                db.log_decision(sym, "no-trade", f"portfolio limit: {cap_reason}")
                return None
            # Daily brake (-6% by default): new capital entries blocked until 00:00 UTC;
            # open positions keep being managed.
            day0 = guards.utc_midnight_ms(int(time.time() * 1000))
            pnl_today = db.capital_pnl_since(day0)
            if guards.daily_loss_hit(pnl_today, self.capital):
                if self._daily_halt_notified != day0:
                    self._daily_halt_notified = day0
                    notify(f"DAILY BRAKE: PnL today {pnl_today:+.0f} <= "
                           f"-{config.max_daily_loss:.0%} of {self.capital:,.0f}; "
                           f"no new capital entries until 00:00 UTC",
                           "CRITICAL", "live.monitor")
                db.log_event("WARN", "live.monitor",
                             f"{sym} {a.strategy}: daily brake active "
                             f"(PnL today {pnl_today:+.0f}), not opening")
                db.log_decision(sym, "no-trade", "daily loss brake")
                return None

        risk_amt = self.capital * config.risk_per_trade
        notional = risk_amt / stop_pct
        entry_fee = DEFAULT_COSTS.fee(notional, maker=False)
        pid = db.log_prediction(sym, score=(80 if a.conviction == "high" else 60),
                                stop=stop, tp=tp,
                                components={"strategy": a.strategy, "side": side,
                                            "observe": observe})
        action = "enter-observe" if observe else "enter"
        db.log_decision(sym, action, f"{a.strategy} {side} entry~{entry:.6g}", prediction_id=pid)
        st = self.states[(sym, a.strategy)]
        # timeout = max_hold signal bars (same as the honest engine): the position does
        # NOT live forever; it is closed at market when the horizon expires.
        sig_tf_h = S.REGISTRY[a.strategy]["signal_tf_h"]
        deadline_ts = sig_close + a.max_hold_signal_bars * sig_tf_h * _H
        st.position = {"side": side, "entry": entry, "stop": stop, "init_stop": stop, "tp": tp,
                       "entry_ts": sig_close, "stop_pct": stop_pct, "notional": notional,
                       "entry_fee": entry_fee, "risk_amt": risk_amt, "strategy": a.strategy,
                       "deadline_ts": deadline_ts, "observe": observe}
        st.last_15m_ts = sig_close
        tag = "OBSERVE" if observe else "ENTER"
        tp_txt = f"{tp:.6g}" if tp is not None else "runner"
        msg = (f"{tag} {sym} {side.upper()} [{a.strategy}] @ {entry:.6g} | "
               f"stop {stop:.6g} tp {tp_txt}")
        notify(msg, "INFO", "live.monitor")
        return {"kind": "ENTER_OBS" if observe else "ENTER",
                "sym": sym, "strategy": a.strategy, "msg": msg}

    def _manage(self, sym: str, st: _PosState) -> dict | None:
        pos = st.position
        m15 = store.load_bars(sym, "15m")
        if m15.empty:
            return None
        ts = m15["ts"].to_numpy()
        mask = (ts > st.last_15m_ts)
        if not mask.any():
            return None
        hi = m15["high"].to_numpy(); lo = m15["low"].to_numpy(); cl = m15["close"].to_numpy()
        side, stop = pos["side"], pos["stop"]
        tp_lvl = S.tp_barrier(pos["tp"], side)        # None = runner -> +/-inf, never fires
        deadline = pos.get("deadline_ts")            # None on legacy-format positions
        for k in np.flatnonzero(mask):
            st.last_15m_ts = int(ts[k])
            if side == "long":
                hit_stop, hit_tp = lo[k] <= stop, hi[k] >= tp_lvl
            else:
                hit_stop, hit_tp = hi[k] >= stop, lo[k] <= tp_lvl
            if hit_stop:                              # pessimistic: stop before time/tp
                return self._close(sym, st, stop, int(ts[k]), "stop")
            if deadline is not None and ts[k] >= deadline:
                return self._close(sym, st, float(cl[k]), int(ts[k]), "timeout")
            if hit_tp:
                return self._close(sym, st, tp_lvl, int(ts[k]), "tp")
        return None

    def _close(self, sym: str, st: _PosState, exit_px: float, exit_ts: int, reason: str) -> dict:
        pos = st.position
        side = pos["side"]
        maker_exit = (reason == "tp")            # TP maker, stop/timeout taker (same as engine)
        fund = 0.0
        fdf = store.load_funding(sym)
        if not fdf.empty:
            m = (fdf["ts"] > pos["entry_ts"]) & (fdf["ts"] <= exit_ts)
            if m.any():
                fund = float(sum(DEFAULT_COSTS.funding(pos["notional"], side, r)
                                 for r in fdf.loc[m, "funding_rate"]))
        pnl, exit_fill = DEFAULT_COSTS.realized(side, pos["entry"], exit_px, pos["notional"],
                                                pos["entry_fee"], maker_exit=maker_exit, funding_total=fund)
        risk_amt = pos["risk_amt"]
        R = pnl / risk_amt if risk_amt > 0 else 0.0
        observe = bool(pos.get("observe", False))
        # Exit cost AUDIT (FORWARD_REVIEW #3): breaks R down into pure price / exit
        # slippage / fees / funding, to answer with data whether "stops realize worse
        # than -1R" comes from the model or from something else.
        notional, entry_px = pos["notional"], pos["entry"]
        dirn = 1.0 if side == "long" else -1.0
        exit_fee = DEFAULT_COSTS.fee(notional, maker=maker_exit)
        audit = None
        if risk_amt > 0:
            audit = {
                "r_gross": (exit_px - entry_px) / entry_px * dirn * notional / risk_amt,
                "r_slip_exit": (exit_fill - exit_px) / entry_px * dirn * notional / risk_amt,
                "r_fee_entry": -pos["entry_fee"] / risk_amt,
                "r_fee_exit": -exit_fee / risk_amt,
                "r_funding": -fund / risk_amt,
            }
        # ts = OPEN time (schema semantics). Without it, log_trade falls back to
        # _now_ms() = close time, which corrupts any time-based analysis (audit 07-02:
        # the "post-v0.8" PAXG trade turned out to be opened on 23-Jun under v0.7).
        db.log_trade(sym, side, config.mode.value, ts=pos["entry_ts"],
                     entry=entry_px, stop=pos["init_stop"],
                     tp=pos["tp"], exit=exit_fill, exit_ts=exit_ts, status="closed", size=notional,
                     strategy=pos["strategy"], r_multiple=R, pnl=pnl,
                     fees=pos["entry_fee"] + exit_fee, funding=fund,
                     observe=observe, exit_reason=reason, cost_audit=audit)
        if reason == "stop":
            kind = "EXIT"
        elif reason == "timeout":
            kind = "TIME_EXIT"
        else:
            kind = "TAKE_PROFIT"
        obs_tag = " (observe)" if observe else ""
        msg = f"{kind}{obs_tag} {sym} [{pos['strategy']}] @ {exit_fill:.6g} | {R:+.2f}R ({reason})"
        notify(msg, "INFO", "live.monitor")
        st.position = None
        return {"kind": kind, "sym": sym, "strategy": pos["strategy"], "msg": msg, "R": R}

    # ------------------------------ state ------------------------------
    def snapshot(self) -> list[dict]:
        out = []
        for (sym, strat), st in self.states.items():
            out.append({"sym": sym, "strategy": strat,
                        "in_trade": st.position is not None,
                        "position": ({"side": st.position["side"], "entry": st.position["entry"],
                                      "stop": st.position["stop"], "tp": st.position["tp"],
                                      "observe": st.position.get("observe", False)}
                                     if st.position else None)})
        return out
