"""Clasificación de régimen (Fase 3): rango | tendencia | caos.

Combina varias señales independientes (ADX, Hurst, variance ratio, R² del
canal y pendiente, ancho de Bollinger) para decidir el régimen y entregar una
`range_quality` continua 0..1 que el scoring usa directamente.

Solo se opera lo predecible (CLAUDE.md): si no hay claridad ⇒ 'chaos' ⇒ no operar.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from oscilion.features import indicators as ind
from oscilion.features import ranges as rng
from oscilion.features import reversion as rev

# umbrales (ajustables; documentados en RISK/VISION)
ADX_TREND = 25.0     # ADX ≥ ⇒ hay tendencia
ADX_RANGE = 20.0     # ADX < ⇒ sin tendencia
R2_TREND = 0.55      # R² del canal alto ⇒ direccional limpio


@dataclass
class RegimeResult:
    regime: str                       # range | trend | chaos
    range_quality: float              # 0..1
    vol_regime: str                   # low | normal | high
    atr_pct: float
    metrics: dict = field(default_factory=dict)


def _vol_regime(df: pd.DataFrame, n: int = 14, lookback: int = 240) -> tuple[str, float]:
    series = ind.atr_pct(df, n).dropna()
    if series.empty:
        return "normal", float("nan")
    cur = float(series.iloc[-1])
    hist = series.tail(lookback)
    lo, hi = np.quantile(hist, 0.33), np.quantile(hist, 0.66)
    reg = "low" if cur <= lo else "high" if cur >= hi else "normal"
    return reg, cur


def classify_regime(df: pd.DataFrame, lookback: int = 96) -> RegimeResult:
    if len(df) < 30:
        return RegimeResult("chaos", 0.0, "normal", float("nan"),
                            {"reason": "datos insuficientes"})

    adx_last = float(ind.adx(df).iloc[-1]["adx"])
    bb = ind.bollinger(df["close"]).iloc[-1]
    chan = rng.diagonal_channel(df, lookback)
    hz = rng.horizontal_range(df, lookback)
    h = rev.hurst(df["close"].tail(lookback))
    vr = rev.variance_ratio(df["close"].tail(lookback), 4)
    vol_reg, atrp = _vol_regime(df)

    r2 = chan["r2"]
    slope_pct = abs(chan["slope_pct"]) if np.isfinite(chan["slope_pct"]) else 0.0

    # --- decisión de régimen ---
    trend_like = (adx_last >= ADX_TREND) and (r2 >= R2_TREND)
    range_like = (adx_last < ADX_RANGE) and (np.isfinite(h) and h < 0.5)

    if trend_like and not range_like:
        regime = "trend"
    elif range_like and not trend_like:
        regime = "range"
    elif not trend_like and not range_like:
        # ni claramente tendencia ni rango limpio
        regime = "range" if hz["quality"] > 0.5 else "chaos"
    else:
        regime = "chaos"

    # --- range_quality continua (0..1) ---
    s_adx = _clamp01((ADX_TREND - adx_last) / ADX_TREND)         # menos ADX, mejor
    s_hurst = _clamp01((0.5 - h) / 0.3) if np.isfinite(h) else 0.0
    s_vr = _clamp01((1.0 - vr) / 0.4) if np.isfinite(vr) else 0.0
    s_hz = float(hz["quality"])
    s_flat = _clamp01(1.0 - slope_pct / max(hz["width_pct"], 1e-9)) if np.isfinite(hz["width_pct"]) else 0.0
    range_quality = float(np.mean([s_adx, s_hurst, s_vr, s_hz, s_flat]))
    if regime == "chaos":
        range_quality *= 0.3                                      # penaliza el caos

    return RegimeResult(
        regime=regime, range_quality=range_quality, vol_regime=vol_reg, atr_pct=atrp,
        metrics={"adx": adx_last, "r2": r2, "slope_pct": chan["slope_pct"],
                 "hurst": h, "variance_ratio": vr, "bb_bandwidth": float(bb["bb_bandwidth"]),
                 "hz_quality": hz["quality"], "hz_width_pct": hz["width_pct"]},
    )


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))
