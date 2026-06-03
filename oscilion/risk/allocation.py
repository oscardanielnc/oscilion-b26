"""Asignación de cartera (RISK_MODEL.md §5).

peso_i ∝ f(convicción_i, 1/volatilidad_i, correlación_entre_elegidas)

- Convicción (score) → más capital al más probable.
- Volatilidad → menos a la más errática.
- Correlación ⚠️ → 3 longs correlacionados = 1 apuesta triplicada. Se penaliza.
- Kelly fraccionado: acota el tamaño total; nunca al 100% por defecto.

Cada moneda mantiene su −2%/+5% sobre SU margen; esto reparte el capital total.
"""
from __future__ import annotations

import numpy as np

from config import config

KELLY_FRACTION = 0.5     # fracción de Kelly (conservador)
MAX_TOTAL_EXPOSURE = 1.0  # fracción máx del capital desplegada a la vez


def allocate(candidates: list[dict], capital: float, *,
             corr: dict[tuple[str, str], float] | None = None,
             max_concurrent: int | None = None) -> list[dict]:
    """Reparte `capital` entre candidatos operables.

    Cada candidato requiere: sym, score (0-100), vol (>0). Devuelve la lista
    (top max_concurrent) con `weight` y `margin` (capital asignado) añadidos.
    """
    max_concurrent = max_concurrent or config.max_concurrent
    elegibles = [c for c in candidates if c.get("tradeable") and c.get("score", 0) > 0
                 and c.get("vol", 0) > 0]
    if not elegibles:
        return []

    # 1) convicción × inverso de volatilidad
    elegibles.sort(key=lambda c: c["score"], reverse=True)
    chosen = elegibles[:max_concurrent]
    raw = np.array([c["score"] * (1.0 / c["vol"]) for c in chosen], dtype="float64")

    # 2) haircut por correlación con las demás elegidas
    if corr:
        hair = []
        for i, ci in enumerate(chosen):
            penalties = [abs(corr.get(_key(ci["sym"], cj["sym"]), 0.0))
                         for j, cj in enumerate(chosen) if j != i]
            avg_corr = float(np.mean(penalties)) if penalties else 0.0
            hair.append(1.0 / (1.0 + avg_corr * (len(chosen) - 1)))
        raw = raw * np.array(hair)

    # 3) normalizar + Kelly fraccionado + techo de exposición
    weights = raw / raw.sum() if raw.sum() > 0 else raw
    deploy = min(MAX_TOTAL_EXPOSURE, KELLY_FRACTION + 0.0)  # conservador
    weights = weights * deploy

    out = []
    for c, w in zip(chosen, weights):
        c = {**c, "weight": float(w), "margin": float(w * capital)}
        out.append(c)
    return out


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)
