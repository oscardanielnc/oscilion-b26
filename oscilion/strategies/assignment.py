"""Mapa moneda → estrategia(s) — la DIRECCIÓN confirmada de Oscilion (v1 pilot).

Decidido 2026-06-03 (ver docs/STRATEGY_MAP.md). Cada moneda recibe SOLO la(s)
estrategia(s) que se le validó(aron) en el motor honesto (full + OOS + walk-forward).
Conviccion > cantidad: si no hay edge probado, la moneda NO está aquí.

⚠️ Los `params` y `weight` son del PILOT v1 (config fija validada). Se AFINARÁN en la
fase B (mejores params por moneda, capital, multiplicadores, correlación). No hardcodear
supuestos nuevos sin validarlos con el motor honesto + forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Assign:
    strategy: str
    params: dict
    max_hold_signal_bars: int
    conviction: str                 # alta | media | marginal
    weight: float | None = None     # capital relativo (lo fija B; None = aún sin asignar)
    note: str = ""


# config validada del pilot (entrada fija; tp_r=4 = "dejar correr ganadores")
_EMA = dict(atr_mult_sl=1.5, tp_r=4.0, fresh_gate=True, session_filter=True, rsi_filter=False)
_ORB = dict(range_max_pct=0.015, tp_r=4.0, fresh_gate=True, long_only=False, session_filter=True)


def _ema(conv, note=""):
    return Assign("ema_trend_stack", dict(_EMA), 60, conv, note=note)


def _orb(conv, note=""):
    return Assign("orb_breakout", dict(_ORB), 24, conv, note=note)


# NÚCLEO de alta convicción (full+OOS+WF positivos)
PORTFOLIO: dict[str, list[Assign]] = {
    "BTC/USDT:USDT":  [_ema("alta", "trender limpio; full+0.34/OOS+0.13")],
    "BNB/USDT:USDT":  [_ema("alta", "trender limpio; full+0.13/OOS+0.41")],
    "TRX/USDT:USDT":  [_ema("alta", "full+0.34/OOS+0.14"),
                       _orb("alta", "full+0.18/OOS+0.29; trend Y breakout")],
    "LINK/USDT:USDT": [_orb("alta", "ORB rescata; full+0.20/OOS+0.31")],
    "DOT/USDT:USDT":  [_orb("alta", "ORB rescata; full+0.13/OOS+0.10")],
    # marginales (en observación; pueden activarse tras afinar B / forward)
    # "ADA/USDT:USDT":  [_orb("marginal")],
    # "DOGE/USDT:USDT": [_orb("marginal")],
    # "XRP/USDT:USDT":  [_orb("marginal")],
    # "LTC/USDT:USDT":  [_orb("marginal")],
}


def core_symbols() -> list[str]:
    return list(PORTFOLIO.keys())


def assignments_for(sym: str) -> list[Assign]:
    return PORTFOLIO.get(sym, [])


def all_assignments() -> list[tuple[str, Assign]]:
    return [(sym, a) for sym, lst in PORTFOLIO.items() for a in lst]
