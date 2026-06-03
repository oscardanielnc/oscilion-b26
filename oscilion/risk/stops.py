"""Stop anti-barridas (RISK_MODEL.md §4).

El nivel obvio (borde del rango) es donde cazan stops. El stop seguro va MÁS
ALLÁ del clúster de liquidez + un buffer de ATR (ruido típico de la moneda).
Si queda más lejos, el apalancamiento baja solo (sizing); la pérdida sigue en
el 2%, sin costo de riesgo extra.
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
    basis: str          # de dónde sale el stop


def safe_stop(df: pd.DataFrame, side: str, entry: float, *,
              range_lo: float | None = None, range_hi: float | None = None,
              atr_n: int = 14, buffer_atr: float = 1.0,
              swing_lookback: int = 24) -> StopResult:
    """Stop más allá del swing/clúster reciente + buffer ATR.

    long  → stop = min(borde_inf, swing_low_reciente) − buffer·ATR
    short → stop = max(borde_sup, swing_high_reciente) + buffer·ATR
    """
    a = float(ind.atr(df, atr_n).iloc[-1])
    if not np.isfinite(a) or a <= 0:
        a = entry * 0.005  # fallback prudente

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
