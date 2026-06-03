"""Gestión de salida (Fase 5) — ARCHITECTURE §4.

Sobre un trade abierto y la última vela cerrada decide:
  • stop      → SAL (taker, urgente)
  • break     → ruptura en contra: SAL urgente (taker)
  • tp        → TOMA GANANCIA (maker)
  • partial   → momentum se agota a mitad: TOMA GANANCIA parcial
  • trail     → mover stop a break-even / trailing cuando va a favor
  • hold      → mantener

Devuelve un dict con action, price, reason y (si aplica) nuevo stop.
"""
from __future__ import annotations

import pandas as pd

from oscilion.features import indicators as ind

BREAKEVEN_AT_R = 1.0     # a +1R, subir stop a break-even
TRAIL_AT_R = 1.5         # desde +1.5R, empezar a trailing
PARTIAL_AT_R = 1.5       # tomar parcial si el momentum se agota pasado +1.5R


def _r_multiple(trade: dict, price: float) -> float:
    entry, stop = trade["entry"], trade["init_stop"]
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    move = (price - entry) if trade["side"] == "long" else (entry - price)
    return move / risk


def exit_signal(trade: dict, df: pd.DataFrame) -> dict:
    """Evalúa la salida con el rango de la última vela cerrada."""
    bar = df.iloc[-1]
    side = trade["side"]
    stop = trade["stop"]
    tp = trade["tp"]
    high, low, close = float(bar["high"]), float(bar["low"]), float(bar["close"])

    # 1) STOP / ruptura en contra (urgente, peor caso primero)
    hit_stop = low <= stop if side == "long" else high >= stop
    if hit_stop:
        return {"action": "stop", "price": stop, "urgent": True,
                "reason": "stop tocado / ruptura en contra"}

    # 2) TP en el borde opuesto
    hit_tp = high >= tp if side == "long" else low <= tp
    if hit_tp:
        return {"action": "tp", "price": tp, "urgent": False,
                "reason": "objetivo alcanzado"}

    r = _r_multiple(trade, close)

    # 3) momentum agotado pasado +1.5R sin tocar TP → parcial
    if r >= PARTIAL_AT_R and not trade.get("partial_done") and _momentum_fading(df, side):
        return {"action": "partial", "price": close, "urgent": False,
                "reason": f"momentum se agota a +{r:.1f}R"}

    # 4) trailing / break-even
    new_stop = _trail_stop(trade, df, r)
    if new_stop is not None and _is_tighter(side, new_stop, stop):
        return {"action": "trail", "price": close, "new_stop": new_stop,
                "urgent": False, "reason": f"trailing a +{r:.1f}R"}

    return {"action": "hold", "price": close, "urgent": False, "reason": "mantener"}


def _momentum_fading(df: pd.DataFrame, side: str, rsi_n: int = 14) -> bool:
    rsi = ind.rsi(df["close"], rsi_n)
    if len(rsi) < 3:
        return False
    a, b = rsi.iloc[-1], rsi.iloc[-2]
    return a < b if side == "long" else a > b


def _trail_stop(trade: dict, df: pd.DataFrame, r: float) -> float | None:
    side, entry = trade["side"], trade["entry"]
    atr = float(ind.atr(df).iloc[-1])
    close = float(df["close"].iloc[-1])
    if r >= TRAIL_AT_R:
        return close - atr if side == "long" else close + atr   # trailing por ATR
    if r >= BREAKEVEN_AT_R:
        return entry                                            # break-even
    return None


def _is_tighter(side: str, new_stop: float, stop: float) -> bool:
    return new_stop > stop if side == "long" else new_stop < stop
