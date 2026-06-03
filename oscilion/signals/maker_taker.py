"""Decisión maker vs taker (RISK_MODEL.md §7).

Regla: maker (límite post-only) cuando no hay urgencia y conviene; taker
(mercado) cuando hay urgencia (stop / ruptura en contra). Nunca sacrificar la
certeza de ejecución de un stop por ahorrar comisión.
"""
from __future__ import annotations

# acciones urgentes ⇒ taker (salir YA)
_URGENT = {"stop", "break", "sal", "stop_loss"}


def decide(action: str, *, urgent: bool | None = None) -> str:
    """Devuelve 'maker' o 'taker' para la acción dada."""
    a = (action or "").lower()
    if urgent is True or a in _URGENT:
        return "taker"
    # entrada en borde, take-profit, parcial → maker (paciente, fee 0/bajo)
    return "maker"


def is_taker(action: str, *, urgent: bool | None = None) -> bool:
    return decide(action, urgent=urgent) == "taker"
