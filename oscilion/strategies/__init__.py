"""Oscilion directional strategies (the core the live monitor runs).

Direction set on 2026-06-03: a multi-coin observer running several engines
(EMA_TREND_STACK for clean trenders, ORB_BREAKOUT for alts, ...) that lets
winners run and only trades where a validated edge exists. See docs/STRATEGY_MAP.md.

The signal logic (library) is the SINGLE source of truth: both the backtest
(validation) and the live monitor (production) use it.
"""
from oscilion.strategies.library import REGISTRY, Ctx, TFArrays, aux_at  # noqa: F401
from oscilion.strategies.assignment import (  # noqa: F401
    PORTFOLIO, assignments_for, core_symbols, all_assignments,
)
