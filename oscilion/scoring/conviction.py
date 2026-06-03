"""Score de convicción 0–100 por moneda (Fase 3).

Combina señales independientes en un score interpretable:

  componente        peso   premia
  ───────────────── ────   ─────────────────────────────────────────
  régimen de rango  0.30   range_quality (rango limpio, no tendencia/caos)
  reversión         0.30   Hurst<0.5, VR<1, ADF estacionario, half-life útil
  ubicación         0.25   precio CERCA de un borde (no en medio del rango)
  volatilidad       0.15   vol baja/normal (penaliza vol alta; evita caos)

Determina el `side` por el borde cercano: cerca del inferior ⇒ long; del
superior ⇒ short; en el medio ⇒ sin señal clara (ubicación baja).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from oscilion.features import ranges as rng
from oscilion.features import regime as rg
from oscilion.features import reversion as rev
from oscilion.features import indicators as ind

WEIGHTS = {"regime": 0.30, "reversion": 0.30, "location": 0.25, "vol": 0.15}
EDGE_LONG = 0.35    # position ≤ ⇒ cerca del borde inferior
EDGE_SHORT = 0.65   # position ≥ ⇒ cerca del borde superior


def conviction(df: pd.DataFrame, lookback: int = 96) -> dict:
    """Score 0-100 + side + bordes del rango + componentes, en la última barra."""
    if len(df) < 40:
        return _empty("datos insuficientes")

    regime = rg.classify_regime(df, lookback)
    hz = rng.horizontal_range(df, lookback)
    chan = rng.diagonal_channel(df, lookback)

    # elegir la estructura de rango más fiable
    use_diag = (chan["r2"] >= 0.55) and (hz["quality"] < 0.5)
    edge = chan if use_diag else hz
    lo, hi = edge["lower" if use_diag else "lo"], edge["upper" if use_diag else "hi"]
    position = edge["position"]
    last = float(df["close"].iloc[-1])

    if not np.isfinite(position):
        return _empty("rango no definido")

    # side por cercanía a un borde
    if position <= EDGE_LONG:
        side, loc = "long", _clamp01((EDGE_LONG - position) / EDGE_LONG)
    elif position >= EDGE_SHORT:
        side, loc = "short", _clamp01((position - EDGE_SHORT) / (1 - EDGE_SHORT))
    else:
        side, loc = None, 0.0

    rev_s = rev.reversion_summary(df["close"].tail(lookback))
    vol_score = {"low": 1.0, "normal": 0.85, "high": 0.35}.get(regime.vol_regime, 0.6)

    comps = {
        "regime": float(regime.range_quality),
        "reversion": float(rev_s["reversion_score"]),
        "location": float(loc),
        "vol": float(vol_score),
    }
    raw = sum(WEIGHTS[k] * comps[k] for k in WEIGHTS)
    score = float(100 * raw)
    if regime.regime == "chaos" or side is None:
        score *= 0.4   # sin claridad ⇒ no operar (CLAUDE.md)

    return {
        "score": round(score, 1), "side": side, "regime": regime.regime,
        "vol_regime": regime.vol_regime, "atr": float(ind.atr(df).iloc[-1]),
        "atr_pct": float(regime.atr_pct), "last": last,
        "edge_kind": edge["kind"], "lo": float(lo), "hi": float(hi),
        "mid": float((lo + hi) / 2), "position": float(position),
        "width_pct": float(edge["width_pct"]),
        "components": comps, "reversion": rev_s, "regime_metrics": regime.metrics,
    }


def _empty(reason: str) -> dict:
    return {"score": 0.0, "side": None, "regime": "chaos", "reason": reason,
            "last": np.nan, "lo": np.nan, "hi": np.nan, "atr": np.nan,
            "atr_pct": np.nan, "position": np.nan, "components": {}}


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))
