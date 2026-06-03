"""Sizing y apalancamiento (RISK_MODEL.md §1-2).

Ecuación maestra:  L = riesgo_máx(%) ÷ distancia_stop(%)
⇒ pérdida si salta el stop = riesgo_máx · margen (fijo, p.ej. 2%).
⇒ ganancia a meta = riesgo_máx · RR.

Filtro duro: una moneda con RR < min_rr NO se opera (no es preferencia).
"""
from __future__ import annotations

from dataclasses import dataclass

from config import config

MAX_LEVERAGE = 25.0  # techo de seguridad operativo


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
    tradeable: bool          # cumple RR ≥ min_rr y geometría válida


def leverage(stop_pct: float, risk: float | None = None) -> float:
    """L = riesgo / stop%. Acotado a [0, MAX_LEVERAGE]."""
    risk = config.risk_per_trade if risk is None else risk
    if stop_pct <= 0:
        return 0.0
    return float(min(MAX_LEVERAGE, risk / stop_pct))


def target_from_rr(side: str, entry: float, stop: float, rr: float) -> float:
    """Precio de TP para un RR dado, según la distancia al stop."""
    risk_dist = abs(entry - stop)
    return entry + rr * risk_dist if side == "long" else entry - rr * risk_dist


def compute(side: str, entry: float, stop: float, tp: float,
            risk: float | None = None, min_rr: float | None = None) -> TradeMath:
    """Calcula stop%, profit%, RR, L y si es operable."""
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
    """Tamaño desde el margen asignado a ESE trade.

    notional = margin · L ; pérdida al stop = notional · stop% = margin · riesgo.
    """
    risk = config.risk_per_trade if risk is None else risk
    lev = leverage(stop_pct, risk)
    notional = margin * lev
    return {"margin": margin, "leverage": lev, "notional": notional,
            "risk_amount": margin * risk}
