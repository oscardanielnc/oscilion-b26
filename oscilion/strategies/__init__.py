"""Estrategias direccionales de Oscilion (núcleo de primera clase).

Dirección confirmada (2026-06-03): observador multi-moneda de dos motores
(EMA_TREND_STACK para trenders limpios; ORB_BREAKOUT para alts), que deja correr
ganadores y solo opera donde hay edge validado. Ver docs/STRATEGY_MAP.md.

La lógica de señal (library) es la ÚNICA fuente de verdad: la usan tanto el
backtest (validación) como el monitor en vivo (producción).
"""
from oscilion.strategies.library import REGISTRY, Ctx, TFArrays, aux_at  # noqa: F401
from oscilion.strategies.assignment import (  # noqa: F401
    PORTFOLIO, assignments_for, core_symbols, all_assignments,
)
