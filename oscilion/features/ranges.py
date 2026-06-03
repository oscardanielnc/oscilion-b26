"""Detección de rangos: horizontal y canal diagonal (Fase 3).

Sobre las últimas `lookback` velas cerradas:
  • horizontal_range — banda [lo,hi] robusta a mechas (cuantiles), con métricas
    de calidad: planitud (pendiente ~0), toques de borde y % de cierres dentro.
  • diagonal_channel — regresión lineal de cierres ± k·σ_residual; pendiente,
    R², ancho y posición del precio dentro del canal.

Ambas devuelven dicts con el estado evaluado en la ÚLTIMA barra.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def horizontal_range(df: pd.DataFrame, lookback: int = 96, q: float = 0.05,
                     touch_tol: float = 0.0015) -> dict:
    """Banda horizontal robusta. `touch_tol` = tolerancia relativa de toque."""
    d = df.tail(lookback)
    if len(d) < 10:
        return _empty_range()

    lo = float(np.quantile(d["low"], q))
    hi = float(np.quantile(d["high"], 1 - q))
    mid = (lo + hi) / 2
    if hi <= lo or mid <= 0:
        return _empty_range()

    width_pct = (hi - lo) / mid
    close = d["close"]
    last = float(close.iloc[-1])

    # planitud: pendiente de regresión normalizada ~ 0 en un rango
    x = np.arange(len(close))
    slope = np.polyfit(x, close.to_numpy(), 1)[0]
    slope_pct = slope * len(close) / mid           # deriva total sobre la ventana
    flatness = float(max(0.0, 1.0 - abs(slope_pct) / width_pct)) if width_pct else 0.0

    # toques de cada borde y contención de cierres
    tol = touch_tol
    touches_lo = int((d["low"] <= lo * (1 + tol)).sum())
    touches_hi = int((d["high"] >= hi * (1 - tol)).sum())
    inside = float(((close >= lo) & (close <= hi)).mean())

    # posición del precio en el rango: 0=borde inf, 1=borde sup
    pos = float((last - lo) / (hi - lo))

    # calidad combinada (0..1)
    touch_score = min(1.0, (min(touches_lo, touches_hi)) / 3.0)
    quality = float(np.mean([flatness, touch_score, inside]))

    return {"kind": "horizontal", "lo": lo, "hi": hi, "mid": mid,
            "width_pct": width_pct, "position": pos, "last": last,
            "touches_lo": touches_lo, "touches_hi": touches_hi,
            "inside_frac": inside, "flatness": flatness, "quality": quality}


def diagonal_channel(df: pd.DataFrame, lookback: int = 96, k: float = 2.0) -> dict:
    """Canal diagonal por regresión lineal ± k·σ_residual."""
    d = df.tail(lookback)
    if len(d) < 10:
        return _empty_channel()

    y = d["close"].to_numpy()
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    fit = slope * x + intercept
    resid = y - fit
    sd = float(resid.std(ddof=0))

    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    x_last = len(y) - 1
    center = float(slope * x_last + intercept)
    upper = center + k * sd
    lower = center - k * sd
    last = float(y[-1])
    mid = float(y.mean())
    slope_pct = float(slope * len(y) / mid) if mid else 0.0      # deriva total %
    width_pct = float((upper - lower) / center) if center else 0.0
    pos = float((last - lower) / (upper - lower)) if upper > lower else 0.5

    return {"kind": "diagonal", "slope": float(slope), "slope_pct": slope_pct,
            "intercept": float(intercept), "r2": r2, "resid_sd": sd,
            "center": center, "upper": upper, "lower": lower,
            "width_pct": width_pct, "position": pos, "last": last}


def _empty_range() -> dict:
    return {"kind": "horizontal", "lo": np.nan, "hi": np.nan, "mid": np.nan,
            "width_pct": np.nan, "position": np.nan, "last": np.nan,
            "touches_lo": 0, "touches_hi": 0, "inside_frac": 0.0,
            "flatness": 0.0, "quality": 0.0}


def _empty_channel() -> dict:
    return {"kind": "diagonal", "slope": np.nan, "slope_pct": np.nan,
            "intercept": np.nan, "r2": 0.0, "resid_sd": np.nan, "center": np.nan,
            "upper": np.nan, "lower": np.nan, "width_pct": np.nan,
            "position": np.nan, "last": np.nan}
