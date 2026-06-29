"""Capa de cartera (Fase B) — SCAFFOLD listo para afinar.

Responde (se validará con muchas pruebas, ver docs/B_PORTFOLIO_PLAN.md):
  • cuánto capital a cada moneda×estrategia (weights),
  • qué multiplicador de apalancamiento sobre el capital asignado,
  • mapa de correlaciones para no apostar varias veces a lo mismo,
  • límites duros (máx. concurrentes, exposición total).

⚠️ v1 = equal-weight provisional. NADA aquí es definitivo hasta validarlo con el
motor honesto + forward. No introducir supuestos sin evidencia.
"""
from __future__ import annotations

from dataclasses import dataclass

from oscilion.strategies.assignment import all_assignments

# Config afinada en Fase B (generada por research/phase_b.py). Si no existe, baseline.
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

MAX_TOTAL_EXPOSURE = 1.0      # fracción máx. del capital desplegada a la vez
DEFAULT_LEVERAGE = 1.0        # multiplicador sobre capital asignado (B: sin extra v1)


def key(sym: str, strategy: str) -> str:
    return f"{sym}|{strategy}"


def _is_observe_only(sym: str, strategy: str) -> bool:
    from oscilion.strategies.assignment import assignments_for
    return any(a.strategy == strategy and a.observe_only for a in assignments_for(sym))


def weight_of(sym: str, strategy: str) -> float:
    if _is_observe_only(sym, strategy):
        return 0.0                       # forward-test: nunca recibe capital
    return WEIGHTS.get(key(sym, strategy), 1.0)


def cluster_of(sym: str, strategy: str) -> str:
    return CLUSTERS.get(key(sym, strategy), sym)


def regime_exempt(sym: str, strategy: str) -> bool:
    """True si el combo NO debe llevar el filtro de régimen de mercado (beta de BTC):
    el oro (descorrelacionado, por SÍMBOLO) y las estrategias ANTI-BETA (break_retest,
    que gana por shorts en alts que caen independientes de BTC). FUENTE ÚNICA — la usan
    el monitor live, forward.refresh y research para no divergir (auditoría 06-29)."""
    from config import config
    return (sym in config.regime_exempt_symbols
            or cluster_of(sym, strategy) == "gold"
            or strategy in config.regime_exempt_strategies)


@dataclass
class Allocation:
    sym: str
    strategy: str
    weight: float             # fracción del capital
    leverage: float           # multiplicador (B lo afinará por moneda)


def equal_weights() -> list[Allocation]:
    """Asignación provisional v1: capital igual entre las series del portfolio.
    B reemplazará esto por weights ∝ f(edge medido, 1/vol, correlación, Kelly fracc.)."""
    items = [(s, a) for s, a in all_assignments() if not a.observe_only]
    n = len(items) or 1
    w = 1.0 / n
    return [Allocation(sym, a.strategy, w, DEFAULT_LEVERAGE) for sym, a in items]


# ---------------------------------------------------------------------------
# TODO (Fase B — ver docs/B_PORTFOLIO_PLAN.md):
#   - weights por edge medido (exp_R) × 1/vol × haircut de correlación + Kelly fracc.
#   - leverage por moneda según distancia de stop y régimen de vol.
#   - correlation_map(): agrupar monedas muy correlacionadas (data/reports/correlation_map.md).
#   - simulación de CARTERA (cuenta única, máx concurrentes, exposición) -> Sharpe/DD reales.
#   - todo validado en el motor honesto + forward antes de fijarse.
# ---------------------------------------------------------------------------
