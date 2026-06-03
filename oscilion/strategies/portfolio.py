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

# límites duros del pilot (ajustables en B)
MAX_CONCURRENT = 3            # máx. posiciones simultáneas
MAX_TOTAL_EXPOSURE = 1.0      # fracción máx. del capital desplegada a la vez
DEFAULT_LEVERAGE = 1.0        # multiplicador sobre el capital asignado (a tunear)


@dataclass
class Allocation:
    sym: str
    strategy: str
    weight: float             # fracción del capital
    leverage: float           # multiplicador (B lo afinará por moneda)


def equal_weights() -> list[Allocation]:
    """Asignación provisional v1: capital igual entre las series del portfolio.
    B reemplazará esto por weights ∝ f(edge medido, 1/vol, correlación, Kelly fracc.)."""
    items = all_assignments()
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
