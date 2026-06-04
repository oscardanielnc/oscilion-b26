"""API FastAPI — endpoints de salud y estado (esqueleto Fase 1).

Lee de la DB (la API nunca escribe lógica de trading). El dashboard React
llegará en Fase 6; por ahora sirve /health, /status y los últimos eventos.
"""
from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import DATA_DIR, config
from oscilion import __version__
from oscilion.persistence import db

app = FastAPI(title="Oscilion API", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


@app.get("/state")
def live_state() -> dict:
    """Estado en vivo de la máquina por moneda (publicado por el orquestador)."""
    f = DATA_DIR / "state.json"
    if not f.exists():
        return {"ts": None, "symbols": [], "note": "orquestador no ha publicado estado aún"}
    return json.loads(f.read_text(encoding="utf-8"))


@app.get("/signals")
def signals() -> list[dict]:
    """Señales en vivo curadas por moneda×estrategia (rango/SL/TP/dirección/RSI/checklist)."""
    from oscilion.live.signals import live_signals

    return live_signals()


@app.get("/portfolio")
def portfolio() -> dict:
    """Config de cartera v1: núcleo, weights, clusters, límites."""
    from oscilion.strategies import all_assignments
    from oscilion.strategies import portfolio as P

    series = [{"sym": s, "base": s.split("/")[0], "strategy": a.strategy,
               "conviction": a.conviction, "weight": P.weight_of(s, a.strategy),
               "cluster": P.cluster_of(s, a.strategy)} for s, a in all_assignments()]
    return {"series": series, "max_concurrent": P.MAX_CONCURRENT,
            "max_per_cluster": P.MAX_PER_CLUSTER, "tuned": P._TUNED}


@app.get("/alerts")
def alerts(limit: int = 40) -> list[dict]:
    """Feed de alertas recientes (ENTRA / SAL / TOMA) del monitor."""
    limit = max(1, min(limit, 200))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, level, msg FROM events WHERE module='live.monitor' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/export")
def export_logs(date_from: str | None = None, date_to: str | None = None, fmt: str = "md"):
    """Descarga logs del rango [date_from..date_to] (YYYY-MM-DD, días Lima; default hoy).
    Conciso: sistema + validación forward + trades + alertas + errores. fmt=md|json."""
    from datetime import datetime, timedelta, timezone
    from fastapi import Response
    from oscilion.live import export as ex

    hoy = datetime.now(timezone(timedelta(hours=-5))).strftime("%Y-%m-%d")
    date_from = date_from or hoy
    date_to = date_to or hoy
    if fmt == "json":
        body = ex.build_json(date_from, date_to)
        media, suf = "application/json", "json"
    else:
        body = ex.build_markdown(date_from, date_to)
        media, suf = "text/markdown; charset=utf-8", "md"
    fname = f"oscilion_logs_{date_from}_{date_to}.{suf}"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/forward")
def forward_results() -> list[dict]:
    """Validación forward: backtest vs vivo por moneda×estrategia (Fase A)."""
    from oscilion.live.forward import curve

    return curve()


@app.get("/trades")
def recent_trades(limit: int = 50) -> list[dict]:
    """Trades virtuales cerrados (con estrategia y R) — feed del frontend."""
    limit = max(1, min(limit, 500))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, sym, side, strategy, entry, exit, r_multiple, pnl, status"
            " FROM trades WHERE status='closed' ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/calibration")
def calibration_curve() -> list[dict]:
    """Curva de fiabilidad forward (score predicho vs winrate real)."""
    from oscilion.scoring.calibration import reliability_curve

    return reliability_curve()


@app.get("/candidates")
def candidates() -> list[dict]:
    """Última predicción + decisión por símbolo (ranking más reciente)."""
    with db._lock:
        rows = db.get_connection().execute(
            """
            SELECT p.sym, p.score, p.range_lo, p.range_hi, p.regime,
                   p.stop, p.tp, p.rr, p.leverage, p.ts,
                   d.action, d.reason
            FROM predictions p
            JOIN (SELECT sym, MAX(ts) AS mts FROM predictions GROUP BY sym) last
              ON p.sym = last.sym AND p.ts = last.mts
            LEFT JOIN decisions d
              ON d.prediction_id = p.id
            ORDER BY p.score DESC
            """
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


# --- Frontend estático (build de frontend/dist) servido en "/" (al final, no pisa la API) ---
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
