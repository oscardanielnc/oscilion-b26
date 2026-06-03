"""Máquina de estados por moneda (Fase 5) — ARCHITECTURE §4.

   ESPERANDO ──(borde + candidato operable)──▶ ACERCÁNDOSE
   ACERCÁNDOSE ──(precio se aleja / pierde borde)──▶ ESPERANDO
   ACERCÁNDOSE ──(giro confirmado + RR≥2.5)──▶ EN TRADE   [alerta ENTRA]
   EN TRADE ──(tp/stop/ruptura/timeout)──▶ ESPERANDO      [alerta TOMA/SAL]

En modo monitor (dry-run) NO se opera: se mantiene un TRADE VIRTUAL para medir
calibración forward (predicción vs resultado) y se emiten las 3 alertas de
negocio: ENTRA / TOMA GANANCIA / SAL. Todo se persiste (auditable).
"""
from __future__ import annotations

import logging
from enum import Enum

import pandas as pd

from config import config
from oscilion.analysis import candidate_from_df
from oscilion.backtest.costs import DEFAULT_COSTS
from oscilion.scoring import calibration
from oscilion.signals import exit as exit_mod
from oscilion.signals import maker_taker
from oscilion.signals.entry import entry_signal
from oscilion.persistence import db
from oscilion.notify import notify

log = logging.getLogger(__name__)


class State(str, Enum):
    WAITING = "ESPERANDO"
    APPROACHING = "ACERCÁNDOSE"
    IN_TRADE = "EN_TRADE"


class SymbolStateMachine:
    def __init__(self, sym: str, tf: str | None = None, *,
                 capital: float = 10_000.0, window: int = 320,
                 lookback: int = 96, max_hold_bars: int = 72):
        self.sym = sym
        self.tf = tf or config.base_timeframe
        self.capital = capital
        self.window = window
        self.lookback = lookback
        self.max_hold_bars = max_hold_bars
        self.state = State.WAITING
        self.trade: dict | None = None
        self.last_candidate: dict | None = None
        self._bars_in_trade = 0

    # ----------------------------- paso -----------------------------
    def step(self, df: pd.DataFrame) -> list[dict]:
        """Avanza un tick con las velas YA CERRADAS. Devuelve alertas emitidas."""
        if df is None or len(df) < 50:
            return []
        win = df.tail(self.window)
        cand = candidate_from_df(self.sym, win, tf=self.tf, lookback=self.lookback)
        self.last_candidate = cand
        ts = int(df["ts"].iloc[-1])

        if self.state is State.IN_TRADE:
            return self._manage(df, ts)
        return self._seek(df, cand, ts)

    # --------------------------- buscar -----------------------------
    def _seek(self, df: pd.DataFrame, cand: dict, ts: int) -> list[dict]:
        alerts: list[dict] = []
        if cand.get("tradeable") and cand.get("side"):
            if self.state is State.WAITING:
                self.state = State.APPROACHING
                db.log_decision(self.sym, "acercándose",
                                f"borde {cand['side']} score={cand['score']}")
            es = entry_signal(df, cand)
            if es["enter"]:
                alerts.append(self._open(df, cand, ts))
        else:
            if self.state is State.APPROACHING:
                db.log_decision(self.sym, "esperar", "perdió el borde sin confirmar")
            self.state = State.WAITING
        return alerts

    def _open(self, df: pd.DataFrame, cand: dict, ts: int) -> dict:
        entry = float(df["close"].iloc[-1])
        stop, tp, side = cand["stop"], cand["tp"], cand["side"]
        stop_pct = abs(entry - stop) / entry if entry else 0.0
        notional = (self.capital * config.risk_per_trade / stop_pct) if stop_pct > 0 else 0.0
        execution = maker_taker.decide("entry")  # maker en borde

        pid = db.log_prediction(self.sym, score=cand["score"], range_lo=cand["lo"],
                                range_hi=cand["hi"], regime=cand["regime"], stop=stop,
                                tp=tp, rr=cand["rr"], leverage=cand["leverage"],
                                components=cand.get("components"))
        db.log_decision(self.sym, "entrar",
                        f"giro confirmado score={cand['score']} rr={cand['rr']:.2f} {execution}",
                        prediction_id=pid)

        self.trade = {
            "sym": self.sym, "side": side, "entry": entry, "entry_ts": ts,
            "stop": stop, "init_stop": stop, "tp": tp, "stop_pct": stop_pct,
            "notional": notional, "score": cand["score"], "regime": cand["regime"],
            "leverage": cand["leverage"], "partial_done": False,
            "entry_fee": DEFAULT_COSTS.fee(notional, maker=True),
        }
        self.state = State.IN_TRADE
        self._bars_in_trade = 0
        msg = (f"🟢 ENTRA {self.sym} {side.upper()} @ {entry:.6g} | stop {stop:.6g} "
               f"tp {tp:.6g} | RR {cand['rr']:.2f} L {cand['leverage']:.2f} | {execution}")
        notify(msg, "INFO", "state_machine")
        return {"kind": "ENTRA", "sym": self.sym, "msg": msg}

    # -------------------------- gestionar ---------------------------
    def _manage(self, df: pd.DataFrame, ts: int) -> list[dict]:
        self._bars_in_trade += 1
        ex = exit_mod.exit_signal(self.trade, df)
        action = ex["action"]

        if action == "trail":
            self.trade["stop"] = ex["new_stop"]
            db.log_event("INFO", "state_machine",
                         f"{self.sym} trailing stop -> {ex['new_stop']:.6g}")
            return []

        if action == "partial" and not self.trade["partial_done"]:
            self.trade["partial_done"] = True
            msg = f"🟡 TOMA GANANCIA parcial {self.sym} @ {ex['price']:.6g} ({ex['reason']})"
            notify(msg, "INFO", "state_machine")
            return [{"kind": "TOMA_GANANCIA", "sym": self.sym, "msg": msg}]

        if action in ("stop", "tp") or self._bars_in_trade >= self.max_hold_bars:
            reason = ex["reason"] if action in ("stop", "tp") else "timeout"
            exit_px = ex["price"] if action in ("stop", "tp") else float(df["close"].iloc[-1])
            return [self._close(exit_px, ts, action if action in ("stop", "tp") else "timeout", reason)]

        return []  # hold

    def _close(self, exit_px: float, ts: int, reason: str, detail: str) -> dict:
        t = self.trade
        side, entry, notional = t["side"], t["entry"], t["notional"]
        price_ret = (exit_px - entry) / entry if side == "long" else (entry - exit_px) / entry
        maker = not maker_taker.is_taker(reason)
        fees = t["entry_fee"] + DEFAULT_COSTS.fee(notional, maker=maker)
        pnl = price_ret * notional - fees

        db.log_trade(self.sym, side, config.mode.value, entry=entry, stop=t["init_stop"],
                     tp=t["tp"], leverage=t["leverage"], size=notional, exit=exit_px,
                     exit_ts=ts, pnl=pnl, fees=fees, status="closed")
        calibration.update_from_trade({"score": t["score"], "pnl": pnl})

        kind = "SAL" if reason in ("stop", "timeout") else "TOMA_GANANCIA"
        icon = "🔴" if kind == "SAL" else "🟢"
        execution = maker_taker.decide(reason)
        msg = (f"{icon} {kind} {self.sym} {side.upper()} @ {exit_px:.6g} | "
               f"{detail} | PnL {pnl:+.2f} ({price_ret*100:+.2f}%) | {execution}")
        notify(msg, "INFO", "state_machine")

        self.trade = None
        self.state = State.WAITING
        self._bars_in_trade = 0
        return {"kind": kind, "sym": self.sym, "msg": msg, "pnl": pnl}

    # --------------------------- estado -----------------------------
    def snapshot(self) -> dict:
        c = self.last_candidate or {}
        return {"sym": self.sym, "state": self.state.value,
                "score": c.get("score"), "side": c.get("side"),
                "regime": c.get("regime"), "position": c.get("position"),
                "in_trade": self.trade is not None,
                "trade": {k: self.trade[k] for k in ("side", "entry", "stop", "tp")} if self.trade else None}
