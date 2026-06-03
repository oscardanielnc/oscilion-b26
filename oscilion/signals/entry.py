"""Señal de entrada con CONFIRMACIÓN DE GIRO (Fase 5).

La pieza que faltaba en la lógica naïve (Fase 4): no basta con tocar el borde;
hay que ver que el precio efectivamente GIRA. Esto evita entrar en cuchillos
que caen (el borde se perfora y sigue).

Confirmación de giro (long, cerca del borde inferior):
  • vela alcista (close > open),
  • cierre subiendo (close > close previo),
  • RSI girando al alza (momentum dejando de caer),
  • reclamo del borde: el cierre vuelve por encima del borde inferior.
(Simétrico para short en el borde superior.)
"""
from __future__ import annotations

import pandas as pd

from oscilion.features import indicators as ind


def confirm_turn(df: pd.DataFrame, side: str, *, edge: float | None = None,
                 rsi_n: int = 14) -> tuple[bool, dict]:
    """¿La última vela cerrada confirma el giro? Devuelve (ok, detalle)."""
    if len(df) < rsi_n + 3:
        return False, {"reason": "datos insuficientes"}

    c, o = df["close"], df["open"]
    rsi = ind.rsi(c, rsi_n)
    last, prev = c.index[-1], c.index[-2]

    if side == "long":
        bullish = c[last] > o[last]
        up = c[last] > c[prev]
        rsi_up = rsi[last] > rsi[prev]
        reclaim = (edge is None) or (c[last] >= edge)
        ok = bool(bullish and up and rsi_up and reclaim)
        detail = {"bullish": bool(bullish), "up": bool(up),
                  "rsi_up": bool(rsi_up), "reclaim": bool(reclaim)}
    else:
        bearish = c[last] < o[last]
        down = c[last] < c[prev]
        rsi_down = rsi[last] < rsi[prev]
        reclaim = (edge is None) or (c[last] <= edge)
        ok = bool(bearish and down and rsi_down and reclaim)
        detail = {"bearish": bool(bearish), "down": bool(down),
                  "rsi_down": bool(rsi_down), "reclaim": bool(reclaim)}
    return ok, detail


def entry_signal(df: pd.DataFrame, candidate: dict) -> dict:
    """Combina candidato operable (Fase 3) + confirmación de giro (Fase 5)."""
    if not candidate.get("tradeable") or not candidate.get("side"):
        return {"enter": False, "reason": "candidato no operable"}

    side = candidate["side"]
    edge = candidate.get("lo") if side == "long" else candidate.get("hi")
    confirmed, detail = confirm_turn(df, side, edge=edge)
    return {
        "enter": bool(confirmed), "confirmed": confirmed, "side": side,
        "price": candidate.get("entry"), "detail": detail,
        "reason": "giro confirmado" if confirmed else "esperando giro",
    }
