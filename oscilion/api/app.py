"""FastAPI app: read-only endpoints for the dashboard.

Reads from the DB and the orchestrator's state file; the API never runs trading
logic. The built React dashboard (frontend/dist) is served at "/".
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import DATA_DIR, config
from oscilion import __version__
from oscilion.persistence import db


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Oscilion API", version=__version__, lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
    """Status/audit of the downloaded history."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT exchange, sym, tf, source, rows, gaps, dupes, first_ts, last_ts, updated_at"
            " FROM ohlcv_status ORDER BY sym, source, tf"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/state")
def live_state() -> dict:
    """Live state per coin (published by the orchestrator)."""
    f = DATA_DIR / "state.json"
    if not f.exists():
        return {"ts": None, "symbols": [], "note": "the orchestrator has not published any state yet"}
    return json.loads(f.read_text(encoding="utf-8"))


@app.get("/signals")
def signals() -> list[dict]:
    """Curated live signals per coin x strategy (range/SL/TP/direction/RSI/checklist)."""
    from oscilion.live.signals import live_signals

    return live_signals()


@app.get("/portfolio")
def portfolio() -> dict:
    """Portfolio config: core, weights, clusters, limits."""
    from oscilion.strategies import all_assignments
    from oscilion.strategies import portfolio as P

    series = [{"sym": s, "base": s.split("/")[0], "strategy": a.strategy,
               "conviction": a.conviction, "weight": P.weight_of(s, a.strategy),
               "cluster": P.cluster_of(s, a.strategy)} for s, a in all_assignments()]
    return {"series": series, "max_concurrent": P.MAX_CONCURRENT,
            "max_per_cluster": P.MAX_PER_CLUSTER, "tuned": P._TUNED}


@app.get("/alerts")
def alerts(limit: int = 40) -> list[dict]:
    """Feed of the monitor's recent alerts (ENTER / EXIT / TAKE_PROFIT)."""
    limit = max(1, min(limit, 200))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, level, msg FROM events WHERE module='live.monitor' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/export")
def export_logs(date_from: str | None = None, date_to: str | None = None, fmt: str = "md"):
    """Download logs for [date_from..date_to] (YYYY-MM-DD, UTC-5 days; default today).
    Concise: system + forward validation + trades + alerts + errors. fmt=md|json."""
    from datetime import datetime
    from fastapi import Response
    from oscilion.live import export as ex

    today = datetime.now(ex.REPORT_TZ).strftime("%Y-%m-%d")
    date_from = date_from or today
    date_to = date_to or today
    if fmt == "json":
        body = ex.build_json(date_from, date_to)
        media, suf = "application/json", "json"
    else:
        body = ex.build_markdown(date_from, date_to)
        media, suf = "text/markdown; charset=utf-8", "md"
    fname = f"oscilion_logs_{date_from}_{date_to}.{suf}"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.get("/snapshots")
def snapshots(limit: int = 200) -> list[dict]:
    """Recent observer snapshots (state/direction/checklist per cycle)."""
    limit = max(1, min(limit, 2000))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, sym, strategy, state, direction, price, checklist_ok, checklist_total,"
            " signal_active, in_trade FROM series_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/forward")
def forward_results() -> list[dict]:
    """Forward validation: backtest vs live per coin x strategy."""
    from oscilion.live.forward import curve

    return curve()


@app.get("/trades")
def recent_trades(limit: int = 50) -> list[dict]:
    """Closed virtual trades (with strategy and R), the dashboard feed."""
    limit = max(1, min(limit, 500))
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT ts, exit_ts, sym, side, strategy, entry, exit, stop, tp, r_multiple, pnl, status,"
            " COALESCE(observe,0) observe, exit_reason, cost_audit"
            " FROM trades WHERE status='closed' ORDER BY COALESCE(exit_ts, ts) DESC LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("cost_audit"):
            try:
                d["cost_audit"] = json.loads(d["cost_audit"])
            except Exception:
                pass
        out.append(d)
    return out


@app.get("/candidates")
def candidates() -> list[dict]:
    """Latest prediction + decision per symbol (most recent ranking)."""
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


# Static dashboard (frontend/dist build) served at "/". Mounted last so it does not shadow the API.
from pathlib import Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
