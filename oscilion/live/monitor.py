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

import numpy as np

from config import config
from oscilion.backtest.costs import DEFAULT_COSTS
from oscilion.data import fetch, store
from oscilion.live import forward
from oscilion.notify import notify
from oscilion.persistence import db
from oscilion.strategies import all_assignments, library as S
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
                 forward_every_ticks: int = 240, snapshot_every_ticks: int = 60):
        self.refresh_data = refresh_data
        self.capital = capital
        self.forward_every_ticks = forward_every_ticks      # ~cada N ticks refresca forward
        self.snapshot_every_ticks = snapshot_every_ticks    # ~cada N ticks deja snapshot (≈horario)
        self.assignments = all_assignments()
        self.symbols = sorted({s for s, _a in self.assignments})
        self._ticks = 0
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

        for sym, a in self.assignments:
            try:
                alerts.extend(self._step_one(sym, a))
            except Exception:
                log.exception("monitor %s %s", sym, a.strategy)
                db.log_event("ERROR", "live.monitor", f"{sym} {a.strategy} falló en tick")
            finally:
                db.save_monitor_state(self._key(sym, a.strategy),
                                      self.states[(sym, a.strategy)].to_dict())

        if self.forward_every_ticks and self._ticks % self.forward_every_ticks == 1:
            try:
                forward.refresh()
            except Exception:
                log.exception("forward refresh")

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
                    r = self._open(sym, a, cand, sig_close)
                    if r:
                        alerts.append(r)
        return alerts

    def _open(self, sym: str, a, cand: dict, sig_close: int) -> dict | None:
        # MISMO método que el engine (forward): entrada taker + slippage, sizing por
        # riesgo, fee de entrada → así los trades del monitor coinciden con la validación.
        side = cand["side"]
        entry = DEFAULT_COSTS.fill_price(float(cand["entry_ref"]), side, is_entry=True, maker=False)
        stop, tp = float(cand["stop"]), float(cand["tp"])
        risk_dist = (entry - stop) if side == "long" else (stop - entry)
        if risk_dist <= 0:
            return None
        stop_pct = risk_dist / entry
        risk_amt = self.capital * config.risk_per_trade
        notional = risk_amt / stop_pct
        entry_fee = DEFAULT_COSTS.fee(notional, maker=False)
        pid = db.log_prediction(sym, score=(80 if a.conviction == "alta" else 60),
                                stop=stop, tp=tp, components={"strategy": a.strategy, "side": side})
        db.log_decision(sym, "entrar", f"{a.strategy} {side} entry≈{entry:.6g}", prediction_id=pid)
        st = self.states[(sym, a.strategy)]
        # timeout = max_hold barras de señal (igual que el engine honesto) → la posición
        # NO vive para siempre; se cierra a mercado al vencer el horizonte.
        sig_tf_h = S.REGISTRY[a.strategy]["signal_tf_h"]
        deadline_ts = sig_close + a.max_hold_signal_bars * sig_tf_h * _H
        st.position = {"side": side, "entry": entry, "stop": stop, "init_stop": stop, "tp": tp,
                       "entry_ts": sig_close, "stop_pct": stop_pct, "notional": notional,
                       "entry_fee": entry_fee, "risk_amt": risk_amt, "strategy": a.strategy,
                       "deadline_ts": deadline_ts}
        st.last_15m_ts = sig_close
        msg = (f"🟢 ENTRA {sym} {side.upper()} [{a.strategy}] @ {entry:.6g} | "
               f"stop {stop:.6g} tp {tp:.6g}")
        notify(msg, "INFO", "live.monitor")
        return {"kind": "ENTRA", "sym": sym, "strategy": a.strategy, "msg": msg}

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
        side, stop, tp = pos["side"], pos["stop"], pos["tp"]
        deadline = pos.get("deadline_ts")            # None en posiciones de formato previo
        for k in np.flatnonzero(mask):
            st.last_15m_ts = int(ts[k])
            if side == "long":
                hit_stop, hit_tp = lo[k] <= stop, hi[k] >= tp
            else:
                hit_stop, hit_tp = hi[k] >= stop, lo[k] <= tp
            if hit_stop:                              # pesimista: stop antes que tiempo/tp
                return self._close(sym, st, stop, int(ts[k]), "stop")
            if deadline is not None and ts[k] >= deadline:
                return self._close(sym, st, float(cl[k]), int(ts[k]), "timeout")
            if hit_tp:
                return self._close(sym, st, tp, int(ts[k]), "tp")
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
        R = pnl / pos["risk_amt"] if pos["risk_amt"] > 0 else 0.0
        db.log_trade(sym, side, config.mode.value, entry=pos["entry"], stop=pos["init_stop"],
                     tp=pos["tp"], exit=exit_fill, exit_ts=exit_ts, status="closed", size=pos["notional"],
                     strategy=pos["strategy"], r_multiple=R, pnl=pnl, funding=fund)
        if reason == "stop":
            kind, icon = "SAL", "🔴"
        elif reason == "timeout":
            kind, icon = "CIERRE_TIEMPO", "⏱️"
        else:
            kind, icon = "TOMA_GANANCIA", "🟢"
        msg = f"{icon} {kind} {sym} [{pos['strategy']}] @ {exit_fill:.6g} | {R:+.2f}R ({reason})"
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
                                      "stop": st.position["stop"], "tp": st.position["tp"]}
                                     if st.position else None)})
        return out
