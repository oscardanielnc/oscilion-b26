"""Helper de confirmación de giro (reutilizable).

`confirm_turn` lo usa el motor de backtest de research (engine.py, gate opcional
`require_confirmation`). Las estrategias direccionales del núcleo (EMA_TREND_STACK,
ORB_BREAKOUT) traen su propia lógica de entrada y NO dependen de esto.
"""
from __future__ import annotations

import pandas as pd

from oscilion.features import indicators as ind


def confirm_turn(df: pd.DataFrame, side: str, *, edge: float | None = None,
                 rsi_n: int = 14) -> tuple[bool, dict]:
    """¿La última vela cerrada confirma el giro? (vela + momentum + RSI + reclamo)."""
    if len(df) < rsi_n + 3:
        return False, {"reason": "datos insuficientes"}
    c, o = df["close"], df["open"]
    rsi = ind.rsi(c, rsi_n)
    last, prev = c.index[-1], c.index[-2]
    if side == "long":
        ok = bool(c[last] > o[last] and c[last] > c[prev] and rsi[last] > rsi[prev]
                  and (edge is None or c[last] >= edge))
        return ok, {}
    ok = bool(c[last] < o[last] and c[last] < c[prev] and rsi[last] < rsi[prev]
              and (edge is None or c[last] <= edge))
    return ok, {}
