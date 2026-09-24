"""Turn confirmation helper.

`confirm_turn` is used by the range-reversion backtest engine (engine.py, optional
`require_confirmation` gate). The directional core strategies (EMA_TREND_STACK,
ORB_BREAKOUT, ...) have their own entry logic and do NOT depend on it.
"""
from __future__ import annotations

import pandas as pd

from oscilion.features import indicators as ind


def confirm_turn(df: pd.DataFrame, side: str, *, edge: float | None = None,
                 rsi_n: int = 14) -> tuple[bool, dict]:
    """Does the last closed candle confirm the turn? (candle + momentum + RSI + reclaim)."""
    if len(df) < rsi_n + 3:
        return False, {"reason": "insufficient data"}
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
