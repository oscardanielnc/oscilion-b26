"""API FastAPI — endpoints de salud y estado (esqueleto Fase 1).

Lee de la DB (la API nunca escribe lógica de trading). El dashboard React
llegará en Fase 6; por ahora sirve /health, /status y los últimos eventos.
"""
from __future__ import annotations

from fastapi import FastAPI

from config import config
from oscilion import __version__
from oscilion.persistence import db

app = FastAPI(title="Oscilion API", version=__version__)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "mode": config.mode.value}


@app.get("/status")
def status() -> dict:
    return {
        "version": __version__,
        "mode": config.mode.value,
        "symbols": config.symbols,
        "risk": {
            "risk_per_trade": config.risk_per_trade,
            "min_profit_target": config.min_profit_target,
            "min_rr": config.min_rr,
        },
        "db_counts": db.counts(),
    }


@app.get("/data")
def data_status() -> list[dict]:
    """Estado/auditoría del histórico descargado (Fase 2)."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT exchange, sym, tf, source, rows, gaps, dupes, first_ts, last_ts, updated_at"
            " FROM ohlcv_status ORDER BY sym, source, tf"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/events")
def events(limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 500))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, level, module, msg FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
