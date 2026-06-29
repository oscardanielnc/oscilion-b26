"""Monitor en vivo (Fase A) — dry-run: recomienda y registra, NO opera.

Por cada (moneda, estrategia) del portfolio confirmado:
  • detecta cuando una nueva vela de señal CERRADA dispara la estrategia → alerta
    ENTRA + registra decisión (trade virtual abierto en memoria);
  • gestiona el trade virtual sobre velas 15m cerradas (stop/TP, pesimista) →
    alerta SAL/TOMA + registra el trade cerrado (con strategy y R) en BD;
  • periódicamente refresca el snapshot de validación forward (backtest vs vivo).

Las MÉTRICAS de validación autoritativas vienen de `live.forward` (motor honesto,
única fuente de verdad). El monitor aporta las alertas en tiempo real y el feed.
Reusa la misma lógica de señal que el backtest (sin divergencia).
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
        self.last_sig_ts = 0       # último cierre de señal procesado
        self.last_15m_ts = 0       # última vela 15m procesada para gestión

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
        self.forward_every_ticks = forward_every_ticks      # ~cada N ticks refresca forward
        self.snapshot_every_ticks = snapshot_every_ticks    # ~cada N ticks deja snapshot (≈horario)
        self.funding_every_ticks = funding_every_ticks      # ~cada 8h refresca funding (settlement)
        self.assignments = all_assignments()
        self.symbols = sorted({s for s, _a in self.assignments})
        self._ticks = 0
        self._daily_halt_notified = None    # día UTC ya notificado del freno diario
        self._mkt_tick = -1                 # cache de régimen de mercado por tick
        self._mkt_bull = None
        # rehidratar estado persistido (sobrevive reinicios → forward-test sin huecos)
        db.init_db()
        saved = db.load_monitor_states()
        self.states = {}
        rehydrated = 0
        for s, a in self.assignments:
            k = self._key(s, a.strategy)
            if k in saved:
                stt = _PosState.from_dict(saved[k])
                # descarta posiciones de un formato anterior (sin los campos de
                # ejecución actuales) para no romper el cierre tras un upgrade.
                if stt.position and "notional" not in stt.position:
                    stt.position = None
                self.states[(s, a.strategy)] = stt
                rehydrated += 1
            else:
                self.states[(s, a.strategy)] = _PosState()
        if rehydrated:
            log.info("monitor: %d series rehidratadas desde BD", rehydrated)

    @staticmethod
    def _key(sym: str, strategy: str) -> str:
        return f"{sym}|{strategy}"

    # ------------------------------ datos ------------------------------
    def _refresh(self, sym: str) -> None:
        # solo velas recientes (la historia ya está sembrada); ligero en red.
        for tf in ("1h", "15m"):
            tf_ms = fetch.timeframe_to_ms(tf)
            since = fetch._now_ms() - 250 * tf_ms
            df = fetch.fetch_ohlcv(sym, tf, since=since)
            if not df.empty:
                store.save_bars(sym, tf, df)

    def _refresh_funding(self, sym: str) -> None:
        # el funding se liquida cada 8h: el _refresh por-tick (OHLCV) NO lo tocaba,
        # así que el parquet quedaba congelado en el último sync_all y los trades
        # vivos cerraban con fund=0 (auditoría 06-29). Lo refrescamos por cadencia.
        since = fetch._now_ms() - 10 * 86_400_000
        f = fetch.fetch_funding(sym, since=since)
        if not f.empty:
            store.save_funding(sym, f)

    def _market_bull(self) -> bool | None:
        """Régimen del benchmark (BTC): True alcista (close>EMA en TF alto), False
        bajista, None si no hay datos. Cacheado por tick (lo consultan N entradas)."""
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

        # forward ANTES de evaluar señales: el gate de validación lee de
        # forward_results, así el primer tick ya decide con datos frescos.
        if self.forward_every_ticks and self._ticks % self.forward_every_ticks == 1:
            try:
                forward.refresh()
            except Exception:
                log.exception("forward refresh")

        # funding por cadencia (~8h): mantiene el parquet al día para que el cierre
        # de trades descuente el funding real y no lo dé por 0.
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
                db.log_event("ERROR", "live.monitor", f"{sym} {a.strategy} falló en tick")
            else:
                # persistir SOLO tras un paso exitoso: si _step_one explotó a mitad,
                # el estado en memoria puede estar corrupto y un restart rehidrataría
                # una posición rota (doble cierre / re-entrada fantasma).
                db.save_monitor_state(self._key(sym, a.strategy),
                                      self.states[(sym, a.strategy)].to_dict())

        # snapshot conciso del observador: por cadencia (≈horario) o en cada cambio
        # (cuando hubo alerta de entrada/salida) → rastro auditable aunque no opere.
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

        # 1) gestionar posición abierta sobre velas 15m nuevas
        if st.position is not None:
            ex = self._manage(sym, st)
            if ex:
                alerts.append(ex)

        # 2) evaluar nueva vela de señal cerrada
        sig_close = int(ctx.sig.ts[i]) + sig_ms
        if sig_close > st.last_sig_ts:
            st.last_sig_ts = sig_close
            if st.position is None:
                cand = S.REGISTRY[a.strategy]["fn"](ctx, i, a.params)
                if cand:
                    # señal vencida: tras downtime/refresh fallido la vela es vieja →
                    # precio de referencia vencido y filtros de sesión ya no valen.
                    if not guards.is_fresh(sig_close, int(time.time() * 1000)):
                        age_min = (int(time.time() * 1000) - sig_close) // 60_000
                        db.log_event("WARN", "live.monitor",
                                     f"{sym} {a.strategy}: señal vencida ({age_min}m > "
                                     f"{config.max_signal_age_min}m) — no se entra")
                        return alerts
                    r = self._open(sym, a, cand, sig_close)
                    if r:
                        alerts.append(r)
        return alerts

    def _open(self, sym: str, a, cand: dict, sig_close: int) -> dict | None:
        # MISMO método que el engine (forward): entrada taker + slippage, sizing por
        # riesgo, fee de entrada → así los trades del monitor coinciden con la validación.
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
                         f"{sym} {a.strategy}: stop_pct {stop_pct:.4%} < piso "
                         f"{config.min_stop_pct:.2%} — no se abre (notional absurdo)")
            return None

        # filtro de COSTO (auditoría 06-29): un stop muy apretado infla el notional y
        # las comisiones se comen la R (oro/TRX). Si el costo round-trip estimado supera
        # el tope, el trade no puede pagar su edge → fuera (capital u observe por igual).
        cost_r = DEFAULT_COSTS.round_trip_cost_r(stop_pct)
        if cost_r > config.max_cost_r:
            db.log_event("WARN", "live.monitor",
                         f"{sym} {a.strategy}: costo {cost_r:.1%} de R > tope "
                         f"{config.max_cost_r:.0%} (stop {stop_pct:.2%} muy apretado) — no se abre")
            db.log_decision(sym, "no-entrar", f"costo-tóxico: {cost_r:.1%} de R (stop {stop_pct:.2%})")
            return None

        # filtro de RÉGIMEN DE MERCADO (auditoría 06-29): no operar a favor de la beta
        # cuando el mercado base va en contra del lado del trade (oro exento). Bloquea
        # las trampas alcistas que costaron −11R en vwap_anchor.
        exempt = P.cluster_of(sym, a.strategy) == "gold"
        regime_block = guards.market_regime_block(
            side, self._market_bull(), enabled=config.market_regime_filter, exempt=exempt)
        if regime_block is not None:
            db.log_event("INFO", "live.monitor",
                         f"{sym} {a.strategy}: régimen — {regime_block} — no se abre")
            db.log_decision(sym, "no-entrar", f"régimen mercado: {regime_block}")
            return None

        # gate de validación (FORWARD_REVIEW #1): sin evidencia local suficiente
        # (n, exp_R del motor honesto) el trade se degrada a observe (sin capital).
        observe, gate_reason = guards.gate_decision(
            db.get_forward_backtest(sym, a.strategy), a.observe_only,
            fw_stats=db.get_forward_result(sym, a.strategy, "forward"))
        if observe and not a.observe_only:
            db.log_event("WARN", "live.monitor",
                         f"{sym} {a.strategy}: degradado a observe — {gate_reason}")
        elif not observe and a.observe_only:
            db.log_event("INFO", "live.monitor",
                         f"{sym} {a.strategy}: GRADUADO a capital por forward — el edge real confirma")

        # guardas de cartera — solo aplican a trades CON capital (observe es stats-only)
        if not observe:
            # veto cruzado (FORWARD_REVIEW #2): 1 posición CON CAPITAL por símbolo.
            other = guards.capital_position_on_symbol(self.states, sym)
            if other is not None:
                db.log_event("INFO", "live.monitor",
                             f"{sym} {a.strategy}: veto símbolo — capital ya abierto en {other}")
                db.log_decision(sym, "no-entrar", f"veto símbolo: posición abierta ({other})")
                return None
            # límites de Fase B (esquema con el que se validó el portfolio): máx 3
            # posiciones con capital, máx 2 por clúster de correlación.
            open_caps = [(s, strat) for (s, strat), st2 in self.states.items()
                         if st2.position is not None and not st2.position.get("observe", False)]
            cap_reason = guards.cluster_cap_reason(open_caps, sym, a.strategy,
                                                   P.cluster_of, P.MAX_CONCURRENT, P.MAX_PER_CLUSTER)
            if cap_reason is not None:
                db.log_event("INFO", "live.monitor",
                             f"{sym} {a.strategy}: límite de cartera — {cap_reason}")
                db.log_decision(sym, "no-entrar", f"límite cartera: {cap_reason}")
                return None
            # freno diario (−6% por defecto): nuevas entradas con capital bloqueadas
            # hasta las 00:00 UTC; las posiciones abiertas se siguen gestionando.
            day0 = guards.utc_midnight_ms(int(time.time() * 1000))
            pnl_today = db.capital_pnl_since(day0)
            if guards.daily_loss_hit(pnl_today, self.capital):
                if self._daily_halt_notified != day0:
                    self._daily_halt_notified = day0
                    notify(f"⛔ FRENO DIARIO: PnL hoy {pnl_today:+.0f} ≤ "
                           f"−{config.max_daily_loss:.0%} de {self.capital:,.0f} — "
                           f"sin nuevas entradas con capital hasta 00:00 UTC",
                           "CRITICAL", "live.monitor")
                db.log_event("WARN", "live.monitor",
                             f"{sym} {a.strategy}: freno diario activo "
                             f"(PnL hoy {pnl_today:+.0f}) — no se abre")
                db.log_decision(sym, "no-entrar", "freno diario de pérdida")
                return None

        risk_amt = self.capital * config.risk_per_trade
        notional = risk_amt / stop_pct
        entry_fee = DEFAULT_COSTS.fee(notional, maker=False)
        pid = db.log_prediction(sym, score=(80 if a.conviction == "alta" else 60),
                                stop=stop, tp=tp,
                                components={"strategy": a.strategy, "side": side,
                                            "observe": observe})
        accion = "entrar-observe" if observe else "entrar"
        db.log_decision(sym, accion, f"{a.strategy} {side} entry≈{entry:.6g}", prediction_id=pid)
        st = self.states[(sym, a.strategy)]
        # timeout = max_hold barras de señal (igual que el engine honesto) → la posición
        # NO vive para siempre; se cierra a mercado al vencer el horizonte.
        sig_tf_h = S.REGISTRY[a.strategy]["signal_tf_h"]
        deadline_ts = sig_close + a.max_hold_signal_bars * sig_tf_h * _H
        st.position = {"side": side, "entry": entry, "stop": stop, "init_stop": stop, "tp": tp,
                       "entry_ts": sig_close, "stop_pct": stop_pct, "notional": notional,
                       "entry_fee": entry_fee, "risk_amt": risk_amt, "strategy": a.strategy,
                       "deadline_ts": deadline_ts, "observe": observe}
        st.last_15m_ts = sig_close
        tag = "👁️ OBSERVA" if observe else "🟢 ENTRA"
        tp_txt = f"{tp:.6g}" if tp is not None else "runner"
        msg = (f"{tag} {sym} {side.upper()} [{a.strategy}] @ {entry:.6g} | "
               f"stop {stop:.6g} tp {tp_txt}")
        notify(msg, "INFO", "live.monitor")
        return {"kind": "ENTRA_OBS" if observe else "ENTRA",
                "sym": sym, "strategy": a.strategy, "msg": msg}

    def _manage(self, sym: str, st: _PosState) -> dict | None:
        pos = st.position
        m15 = store.load_bars(sym, "15m")
        if m15.empty:
            return None
        ts = m15["ts"].to_numpy()
        # velas 15m nuevas desde la última procesada y dentro del trade
        mask = (ts > st.last_15m_ts)
        if not mask.any():
            return None
        hi = m15["high"].to_numpy(); lo = m15["low"].to_numpy(); cl = m15["close"].to_numpy()
        side, stop = pos["side"], pos["stop"]
        tp_lvl = S.tp_barrier(pos["tp"], side)        # None = runner → ±inf, nunca dispara
        deadline = pos.get("deadline_ts")            # None en posiciones de formato previo
        for k in np.flatnonzero(mask):
            st.last_15m_ts = int(ts[k])
            if side == "long":
                hit_stop, hit_tp = lo[k] <= stop, hi[k] >= tp_lvl
            else:
                hit_stop, hit_tp = hi[k] >= stop, lo[k] <= tp_lvl
            if hit_stop:                              # pesimista: stop antes que tiempo/tp
                return self._close(sym, st, stop, int(ts[k]), "stop")
            if deadline is not None and ts[k] >= deadline:
                return self._close(sym, st, float(cl[k]), int(ts[k]), "timeout")
            if hit_tp:
                return self._close(sym, st, tp_lvl, int(ts[k]), "tp")
        return None

    def _close(self, sym: str, st: _PosState, exit_px: float, exit_ts: int, reason: str) -> dict:
        pos = st.position
        side = pos["side"]
        maker_exit = (reason == "tp")            # TP maker, stop/timeout taker (= engine)
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
        # AUDITORÍA de costes de salida (FORWARD_REVIEW #3): descompone el R en
        # precio puro / slippage de salida / fees / funding — responde con datos
        # si "los stops realizan peor que −1R" viene del modelo o de otra cosa.
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
        db.log_trade(sym, side, config.mode.value, entry=entry_px, stop=pos["init_stop"],
                     tp=pos["tp"], exit=exit_fill, exit_ts=exit_ts, status="closed", size=notional,
                     strategy=pos["strategy"], r_multiple=R, pnl=pnl,
                     fees=pos["entry_fee"] + exit_fee, funding=fund,
                     observe=observe, exit_reason=reason, cost_audit=audit)
        if reason == "stop":
            kind, icon = "SAL", "🔴"
        elif reason == "timeout":
            kind, icon = "CIERRE_TIEMPO", "⏱️"
        else:
            kind, icon = "TOMA_GANANCIA", "🟢"
        obs_tag = " (observe)" if observe else ""
        msg = f"{icon} {kind}{obs_tag} {sym} [{pos['strategy']}] @ {exit_fill:.6g} | {R:+.2f}R ({reason})"
        notify(msg, "INFO", "live.monitor")
        st.position = None
        return {"kind": kind, "sym": sym, "strategy": pos["strategy"], "msg": msg, "R": R}

    # ----------------------------- estado ------------------------------
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
