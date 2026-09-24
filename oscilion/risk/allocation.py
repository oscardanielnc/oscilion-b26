"""Portfolio allocation (RISK_MODEL.md section 5).

weight_i ~ f(conviction_i, 1/volatility_i, correlation among the chosen ones)

- Conviction (score): more capital to the most likely setup.
- Volatility: less to the most erratic one.
- Correlation: 3 correlated longs = 1 tripled bet. Penalized.
- Fractional Kelly: caps the total size; never 100% by default.

Each coin keeps its -2%/+5% on ITS margin; this splits the total capital.
"""
from __future__ import annotations

import numpy as np

from config import config

KELLY_FRACTION = 0.5     # conservative
MAX_TOTAL_EXPOSURE = 1.0  # max fraction of capital deployed at once


def allocate(candidates: list[dict], capital: float, *,
             corr: dict[tuple[str, str], float] | None = None,
             max_concurrent: int | None = None) -> list[dict]:
    """Split `capital` among tradeable candidates.

    Each candidate needs: sym, score (0-100), vol (> 0). Returns the list
    (top max_concurrent) with `weight` and `margin` (allocated capital) added.
    """
    max_concurrent = max_concurrent or config.max_concurrent
    eligible = [c for c in candidates if c.get("tradeable") and c.get("score", 0) > 0
                 and c.get("vol", 0) > 0]
    if not eligible:
        return []

    # 1) conviction x inverse volatility
    eligible.sort(key=lambda c: c["score"], reverse=True)
    chosen = eligible[:max_concurrent]
    raw = np.array([c["score"] * (1.0 / c["vol"]) for c in chosen], dtype="float64")

    # 2) haircut for correlation with the other chosen candidates
    if corr:
        hair = []
        for i, ci in enumerate(chosen):
            penalties = [abs(corr.get(_key(ci["sym"], cj["sym"]), 0.0))
                         for j, cj in enumerate(chosen) if j != i]
            avg_corr = float(np.mean(penalties)) if penalties else 0.0
            hair.append(1.0 / (1.0 + avg_corr * (len(chosen) - 1)))
        raw = raw * np.array(hair)

    # 3) normalize + fractional Kelly + exposure cap
    weights = raw / raw.sum() if raw.sum() > 0 else raw
    deploy = min(MAX_TOTAL_EXPOSURE, KELLY_FRACTION)
    weights = weights * deploy

    out = []
    for c, w in zip(chosen, weights):
        c = {**c, "weight": float(w), "margin": float(w * capital)}
        out.append(c)
    return out


def _key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)
