"""Calibración forward (Fase 5): ¿el score se cumple en vivo?

A medida que los trades virtuales (dry-run) o reales cierran, se registra el
resultado por bucket de score. La curva de fiabilidad compara score predicho
vs winrate real → mide si el sistema "sabe lo que cree saber".
"""
from __future__ import annotations

from oscilion.persistence import db


def bucket_of(score: float, width: int = 10) -> int:
    return int(min(90, max(0, score)) // width * width)


def record_outcome(score: float, win: bool) -> None:
    db.update_calibration(bucket_of(score), win)


def update_from_trade(trade: dict) -> None:
    """Registra el resultado de un trade cerrado para calibración."""
    score = trade.get("score")
    pnl = trade.get("pnl")
    if score is None or pnl is None:
        return
    record_outcome(score, pnl > 0)


def reliability_curve() -> list[dict]:
    """Curva de fiabilidad persistida: por bucket, n / winrate real."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT bucket_score, n, hits, ratio_real FROM calibration"
            " WHERE n > 0 ORDER BY bucket_score"
        ).fetchall()
    return [dict(r) for r in rows]
