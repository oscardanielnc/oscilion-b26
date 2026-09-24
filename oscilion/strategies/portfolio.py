"""Portfolio layer: weights, correlation clusters and hard limits per combo.

Answers (see docs/B_PORTFOLIO_PLAN.md):
  - how much capital each coin x strategy combo gets (weights),
  - the correlation map, so the same bet is not placed several times,
  - hard limits (max concurrent positions, max per cluster).

The tuned values live in `tuned.py` (produced by research/phase_b.py). Without
it, the baseline is equal weight with no clusters.
"""
from __future__ import annotations

try:
    from oscilion.strategies import tuned as _t
    WEIGHTS: dict = dict(_t.WEIGHTS)
    CLUSTERS: dict = dict(_t.CLUSTERS)
    MAX_CONCURRENT = int(_t.LIMITS.get("max_concurrent", 3))
    MAX_PER_CLUSTER = int(_t.LIMITS.get("max_per_cluster", 2))
    _TUNED = True
except Exception:
    WEIGHTS, CLUSTERS = {}, {}
    MAX_CONCURRENT, MAX_PER_CLUSTER = 3, 2
    _TUNED = False


def key(sym: str, strategy: str) -> str:
    return f"{sym}|{strategy}"


def _is_observe_only(sym: str, strategy: str) -> bool:
    from oscilion.strategies.assignment import assignments_for
    return any(a.strategy == strategy and a.observe_only for a in assignments_for(sym))


def weight_of(sym: str, strategy: str) -> float:
    if _is_observe_only(sym, strategy):
        return 0.0                       # forward test: never receives capital
    return WEIGHTS.get(key(sym, strategy), 1.0)


def cluster_of(sym: str, strategy: str) -> str:
    return CLUSTERS.get(key(sym, strategy), sym)


def regime_exempt(sym: str, strategy: str) -> bool:
    """True if the combo must NOT carry the market regime filter (BTC beta): gold
    (uncorrelated, per SYMBOL) and the ANTI-BETA strategies (break_retest, which wins
    by shorting alts that fall independently of BTC). SINGLE SOURCE, used by the live
    monitor, forward.refresh and research so they cannot diverge (audit 06-29)."""
    from config import config
    return (sym in config.regime_exempt_symbols
            or cluster_of(sym, strategy) == "gold"
            or strategy in config.regime_exempt_strategies)
