"""Sizing and leverage (RISK_MODEL.md sections 1-2).

Master equation:  L = max_risk(%) / stop_distance(%)
=> loss if the stop fires = max_risk * margin (fixed, e.g. 2%).
=> gain at target = max_risk * RR.

Hard filter: a coin with RR < min_rr is NOT traded (not a preference).
"""
from __future__ import annotations

from dataclasses import dataclass

from config import config

MAX_LEVERAGE = 25.0  # operational safety ceiling


@dataclass
class TradeMath:
    side: str
    entry: float
    stop: float
    tp: float
    stop_pct: float
    profit_pct: float
    rr: float
    leverage: float
    tradeable: bool          # RR >= min_rr and valid geometry


def leverage(stop_pct: float, risk: float | None = None) -> float:
    """L = risk / stop%. Bounded to [0, MAX_LEVERAGE]."""
    risk = config.risk_per_trade if risk is None else risk
    if stop_pct <= 0:
        return 0.0
    return float(min(MAX_LEVERAGE, risk / stop_pct))


def compute(side: str, entry: float, stop: float, tp: float,
            risk: float | None = None, min_rr: float | None = None) -> TradeMath:
    """Compute stop%, profit%, RR, L and whether the trade is tradeable."""
    risk = config.risk_per_trade if risk is None else risk
    min_rr = config.min_rr if min_rr is None else min_rr

    if side == "long":
        risk_dist, reward_dist = entry - stop, tp - entry
    else:
        risk_dist, reward_dist = stop - entry, entry - tp

    valid_geom = entry > 0 and risk_dist > 0 and reward_dist > 0
    stop_pct = risk_dist / entry if entry > 0 else 0.0
    profit_pct = reward_dist / entry if entry > 0 else 0.0
    rr = reward_dist / risk_dist if risk_dist > 0 else 0.0
    lev = leverage(stop_pct, risk)
    tradeable = bool(valid_geom and rr >= min_rr and lev > 0)

    return TradeMath(side, entry, stop, tp, stop_pct, profit_pct, rr, lev, tradeable)


def position_size(margin: float, stop_pct: float, risk: float | None = None) -> dict:
    """Size from the margin allocated to THAT trade.

    notional = margin * L; loss at stop = notional * stop% = margin * risk.
    """
    risk = config.risk_per_trade if risk is None else risk
    lev = leverage(stop_pct, risk)
    notional = margin * lev
    return {"margin": margin, "leverage": lev, "notional": notional,
            "risk_amount": margin * risk}
