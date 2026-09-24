"""Anti-sweep stop (RISK_MODEL.md section 4).

The obvious level (the range edge) is where stops get hunted. The safe stop goes
BEYOND the liquidity cluster + an ATR buffer (the coin's typical noise). If that
puts it further away, leverage drops automatically (sizing); the loss stays at
2%, with no extra risk cost.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from oscilion.features import indicators as ind


@dataclass
class StopResult:
    stop: float
    stop_pct: float
    basis: str          # where the stop comes from


def safe_stop(df: pd.DataFrame, side: str, entry: float, *,
              range_lo: float | None = None, range_hi: float | None = None,
              atr_n: int = 14, buffer_atr: float = 1.0,
              swing_lookback: int = 24) -> StopResult:
    """Stop beyond the recent swing/cluster + an ATR buffer.

    long  -> stop = min(lower_edge, recent_swing_low) - buffer * ATR
    short -> stop = max(upper_edge, recent_swing_high) + buffer * ATR
    """
    a = float(ind.atr(df, atr_n).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        a = entry * 0.005  # conservative fallback

    tail = df.tail(swing_lookback)
    swing_low = float(tail["low"].min())
    swing_high = float(tail["high"].max())

    if side == "long":
        cluster = min(swing_low, range_lo) if range_lo is not None else swing_low
        stop = cluster - buffer_atr * a
        basis = "swing_low+atr" if (range_lo is None or swing_low < range_lo) else "range_lo+atr"
    else:
        cluster = max(swing_high, range_hi) if range_hi is not None else swing_high
        stop = cluster + buffer_atr * a
        basis = "swing_high+atr" if (range_hi is None or swing_high > range_hi) else "range_hi+atr"

    stop_pct = abs(entry - stop) / entry if entry > 0 else 0.0
    return StopResult(stop=float(stop), stop_pct=float(stop_pct), basis=basis)
