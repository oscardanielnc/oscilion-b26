"""Pipeline de datos (Fase 2): descarga → limpia → persiste → audita.

`sync_all()` baja OHLCV (todos los TF configurados) + funding para una lista
de símbolos y devuelve un reporte de calidad por símbolo/TF.
`quality_report_md()` formatea el estado persistido (tabla `ohlcv_status`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import config
from oscilion.data import fetch, store
from oscilion.persistence import db

log = logging.getLogger(__name__)


def _since_days(days: int) -> int:
    return fetch._now_ms() - days * 86_400_000


def sync_symbol(sym: str, *, timeframes: list[str], days: int) -> list[dict]:
    """Sincroniza un símbolo: OHLCV por TF + funding. Devuelve resúmenes."""
    since = _since_days(days)
    out: list[dict] = []
    for tf in timeframes:
        try:
            df = fetch.fetch_ohlcv(sym, tf, since=since)
            res = store.save_bars(sym, tf, df)
            out.append(res)
        except Exception:
            log.exception("Fallo sync OHLCV %s %s", sym, tf)
            db.log_event("ERROR", "data.pipeline", f"sync OHLCV {sym} {tf} falló")
    try:
        f = fetch.fetch_funding(sym, since=since)
        store.save_funding(sym, f)
    except Exception:
        log.exception("Fallo sync funding %s", sym)
        db.log_event("ERROR", "data.pipeline", f"sync funding {sym} falló")
    return out


def sync_all(
    symbols: list[str] | None = None, *,
    timeframes: list[str] | None = None, days: int = 365,
) -> list[dict]:
    symbols = symbols or config.symbols
    timeframes = timeframes or [config.base_timeframe, config.fast_timeframe]
    db.init_db()
    log.info("sync_all | %d símbolos | TF=%s | %d días", len(symbols), timeframes, days)
    results: list[dict] = []
    for sym in symbols:
        results.extend(sync_symbol(sym, timeframes=timeframes, days=days))
    db.log_event("INFO", "data.pipeline", f"sync_all completado: {len(results)} series")
    return results


def _fmt_ts(ms: int | None) -> str:
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def quality_report_md() -> str:
    """Reporte de calidad legible desde la tabla de estado persistida."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT sym, tf, source, rows, gaps, dupes, first_ts, last_ts, updated_at"
            " FROM ohlcv_status ORDER BY sym, source, tf"
        ).fetchall()

    if not rows:
        return "_Sin datos persistidos todavía. Corre `python -m oscilion.data sync`._"

    lines = [
        "# Reporte de calidad de datos",
        "",
        "| Símbolo | TF | Fuente | Filas | Huecos | Dups | Desde | Hasta |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['sym']} | {r['tf']} | {r['source']} | {r['rows']:,} | "
            f"{r['gaps']} | {r['dupes']} | {_fmt_ts(r['first_ts'])} | {_fmt_ts(r['last_ts'])} |"
        )
    total = sum(r["rows"] for r in rows)
    total_gaps = sum(r["gaps"] for r in rows)
    lines += ["", f"**Total filas:** {total:,} · **huecos:** {total_gaps} · "
              f"**series:** {len(rows)}"]
    return "\n".join(lines)
