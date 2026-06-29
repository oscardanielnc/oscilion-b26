"""Conexión SQLite, migraciones idempotentes y API de escritura append-only.

- WAL + connexión compartida thread-safe (lock) → el orquestador y la API
  pueden leer/escribir sin pisarse.
- Solo se exponen `log_*` (INSERT). No hay update/delete de eventos: la
  auditoría es inviolable. `calibration` es la única con upsert (agregado).
- Cada `log_*` es defensivo: si la DB falla, NO debe tumbar el tick (devuelve
  None y deja rastro en el logger), porque la resiliencia manda.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from config import DB_PATH
from oscilion.persistence import models

log = logging.getLogger(__name__)

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def _now_ms() -> int:
    return int(time.time() * 1000)


def get_connection() -> sqlite3.Connection:
    """Conexión única (lazy), con WAL y FK activadas."""
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
                _conn = sqlite3.connect(
                    DB_PATH, check_same_thread=False, isolation_level=None
                )
                _conn.row_factory = sqlite3.Row
                _conn.execute("PRAGMA journal_mode=WAL")
                _conn.execute("PRAGMA synchronous=NORMAL")
                _conn.execute("PRAGMA foreign_keys=ON")
                # API y orquestador son 2 procesos sobre la misma BD: esperar en
                # vez de fallar con SQLITE_BUSY si coinciden escritura/lectura.
                _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


def init_db() -> None:
    """Crea tablas e índices (idempotente) y registra la versión de esquema."""
    conn = get_connection()
    with _lock:
        for ddl in models.TABLES.values():
            conn.execute(ddl)
        for alter in getattr(models, "MIGRATIONS", []):
            try:
                conn.execute(alter)
            except Exception:
                pass  # columna ya existe (migración idempotente)
        for idx in models.INDEXES:
            conn.execute(idx)
        conn.execute(
            "INSERT INTO schema_meta(key, value, updated_at) VALUES('schema_version', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (str(models.SCHEMA_VERSION), _now_ms()),
        )
    log.info("DB lista en %s (schema v%d)", DB_PATH, models.SCHEMA_VERSION)


def _insert(table: str, data: dict[str, Any]) -> Optional[int]:
    """INSERT genérico, defensivo con reintentos. Devuelve el id o None.

    Reintenta ante 'database is locked' (contención entre procesos) además del
    PRAGMA busy_timeout, para NO perder registros críticos (trades/alertas).
    """
    data = {**data, "created_at": _now_ms()}
    cols = ", ".join(data.keys())
    ph = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({ph})"
    vals = tuple(data.values())
    for attempt in range(4):
        try:
            with _lock:
                cur = get_connection().execute(sql, vals)
            return cur.lastrowid
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and attempt < 3:
                time.sleep(0.5 * (attempt + 1))
                continue
            log.error("INSERT %s falló (locked) tras reintentos: %s", table, e)
            return None
        except Exception:  # nunca tumbar el tick por un fallo de persistencia
            log.exception("Fallo al insertar en %s", table)
            return None
    return None


def _jdump(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    return json.dumps(obj, default=str, separators=(",", ":"))


# --------------------------- API append-only ---------------------------
def log_snapshot(
    sym: str, price: float | None = None, *, ts: int | None = None,
    ohlcv_ref: str | None = None, indicators: dict | None = None,
) -> Optional[int]:
    return _insert(
        "market_snapshots",
        dict(ts=ts or _now_ms(), sym=sym, price=price,
             ohlcv_ref=ohlcv_ref, indicators=_jdump(indicators)),
    )


def log_series_snapshot(
    sym: str, strategy: str, *, state: str, direction: str | None = None,
    price: float | None = None, checklist_ok: int | None = None,
    checklist_total: int | None = None, signal_active: bool = False,
    in_trade: bool = False, ts: int | None = None,
) -> Optional[int]:
    """Snapshot conciso por ciclo de lo que ve el observador (append-only)."""
    return _insert(
        "series_snapshots",
        dict(ts=ts or _now_ms(), sym=sym, strategy=strategy, state=state,
             direction=direction, price=price, checklist_ok=checklist_ok,
             checklist_total=checklist_total, signal_active=int(signal_active),
             in_trade=int(in_trade)),
    )


def log_prediction(sym: str, **f: Any) -> Optional[int]:
    f["components"] = _jdump(f.get("components"))
    f.setdefault("ts", _now_ms())
    f["sym"] = sym
    allowed = {"ts", "sym", "score", "range_lo", "range_hi", "regime",
               "stop", "tp", "rr", "leverage", "components"}
    return _insert("predictions", {k: v for k, v in f.items() if k in allowed})


def log_decision(
    sym: str, action: str, reason: str | None = None, *,
    ts: int | None = None, prediction_id: int | None = None,
) -> Optional[int]:
    return _insert(
        "decisions",
        dict(ts=ts or _now_ms(), sym=sym, action=action,
             reason=reason, prediction_id=prediction_id),
    )


def log_trade(sym: str, side: str, mode: str, **f: Any) -> Optional[int]:
    f.setdefault("ts", _now_ms())
    f.update(sym=sym, side=side, mode=mode)
    if "cost_audit" in f:
        f["cost_audit"] = _jdump(f["cost_audit"])
    if "observe" in f:
        f["observe"] = int(bool(f["observe"]))
    allowed = {"ts", "sym", "side", "mode", "entry", "stop", "tp", "leverage",
               "size", "exit", "exit_ts", "pnl", "fees", "funding", "status",
               "strategy", "r_multiple", "observe", "exit_reason", "cost_audit"}
    return _insert("trades", {k: v for k, v in f.items() if k in allowed})


def capital_pnl_since(since_ms: int) -> float:
    """PnL cerrado de trades CON CAPITAL (observe=0) desde `since_ms`.
    Lo usa el freno diario; ante fallo devuelve 0.0 (no frena por error de BD,
    el breaker de errores ya cubre ese caso)."""
    try:
        with _lock:
            row = get_connection().execute(
                "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status='closed'"
                " AND COALESCE(observe, 0)=0 AND exit_ts >= ?", (since_ms,),
            ).fetchone()
        return float(row[0] or 0.0)
    except Exception:
        log.exception("Fallo capital_pnl_since")
        return 0.0


def get_forward_result(sym: str, strategy: str, scope: str) -> Optional[dict]:
    """Stats persistidas del motor honesto para un scope ('backtest' | 'forward').
    None si aún no hay snapshot (forward.refresh no corrió)."""
    try:
        with _lock:
            row = get_connection().execute(
                "SELECT n, win_rate, exp_r, sum_r FROM forward_results"
                " WHERE sym=? AND strategy=? AND scope=?",
                (sym, strategy, scope),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        log.exception("Fallo get_forward_result %s %s %s", sym, strategy, scope)
        return None


def get_forward_backtest(sym: str, strategy: str) -> Optional[dict]:
    """Stats del backtest LOCAL (OOS) para el gate. None → el gate bloquea."""
    return get_forward_result(sym, strategy, "backtest")


def log_params(version: str, params: dict) -> Optional[int]:
    return _insert("params", dict(ts=_now_ms(), version=version,
                                  json_params=_jdump(params) or "{}"))


def log_event(level: str, module: str, msg: str, extra: dict | None = None) -> Optional[int]:
    return _insert("events", dict(ts=_now_ms(), level=level.upper(),
                                  module=module, msg=msg, extra=_jdump(extra)))


def upsert_ohlcv_status(
    exchange: str, sym: str, tf: str, source: str, *,
    first_ts: int | None, last_ts: int | None,
    rows: int, gaps: int = 0, dupes: int = 0,
) -> None:
    """Resumen auditable del histórico por (exchange, sym, tf, source)."""
    try:
        with _lock:
            get_connection().execute(
                "INSERT INTO ohlcv_status"
                " (exchange, sym, tf, source, first_ts, last_ts, rows, gaps, dupes, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(exchange, sym, tf, source) DO UPDATE SET"
                "  first_ts=excluded.first_ts, last_ts=excluded.last_ts, rows=excluded.rows,"
                "  gaps=excluded.gaps, dupes=excluded.dupes, updated_at=excluded.updated_at",
                (exchange, sym, tf, source, first_ts, last_ts, rows, gaps, dupes, _now_ms()),
            )
    except Exception:
        log.exception("Fallo al upsert ohlcv_status %s %s %s", sym, tf, source)


def update_calibration(bucket_score: int, hit: bool) -> None:
    """Acumula resultado real por bucket de score (forward-test, Fase 5)."""
    try:
        with _lock:
            get_connection().execute(
                "INSERT INTO calibration (bucket_score, n, hits, ratio_real, updated_at)"
                " VALUES (?, 1, ?, ?, ?)"
                " ON CONFLICT(bucket_score) DO UPDATE SET"
                "  n = n + 1, hits = hits + excluded.hits,"
                "  ratio_real = CAST(hits + excluded.hits AS REAL) / (n + 1),"
                "  updated_at = excluded.updated_at",
                (int(bucket_score), 1 if hit else 0, 1.0 if hit else 0.0, _now_ms()),
            )
    except Exception:
        log.exception("Fallo update_calibration bucket=%s", bucket_score)


def upsert_forward_result(sym: str, strategy: str, scope: str, *, n: int,
                          win_rate: float | None, exp_r: float | None,
                          sum_r: float | None, last_entry_ts: int | None) -> None:
    """Snapshot conciso de validación (backtest vs forward) por sym×strategy."""
    try:
        with _lock:
            get_connection().execute(
                "INSERT INTO forward_results"
                " (sym, strategy, scope, n, win_rate, exp_r, sum_r, last_entry_ts, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(sym, strategy, scope) DO UPDATE SET"
                "  n=excluded.n, win_rate=excluded.win_rate, exp_r=excluded.exp_r,"
                "  sum_r=excluded.sum_r, last_entry_ts=excluded.last_entry_ts,"
                "  updated_at=excluded.updated_at",
                (sym, strategy, scope, n, win_rate, exp_r, sum_r, last_entry_ts, _now_ms()),
            )
    except Exception:
        log.exception("Fallo upsert_forward_result %s %s %s", sym, strategy, scope)


def save_monitor_state(key: str, state: dict) -> None:
    """Persiste el estado de una serie del monitor (upsert)."""
    try:
        with _lock:
            get_connection().execute(
                "INSERT INTO monitor_state (key, state, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
                (key, _jdump(state) or "{}", _now_ms()),
            )
    except Exception:
        log.exception("Fallo save_monitor_state %s", key)


def load_monitor_states() -> dict[str, dict]:
    """Rehidrata el estado del monitor tras un reinicio."""
    out: dict[str, dict] = {}
    try:
        with _lock:
            rows = get_connection().execute("SELECT key, state FROM monitor_state").fetchall()
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["state"])
            except Exception:
                pass
    except Exception:
        log.exception("Fallo load_monitor_states")
    return out


def counts() -> dict[str, int]:
    """Conteo de filas por tabla (para /status del API y diagnósticos)."""
    out: dict[str, int] = {}
    with _lock:
        conn = get_connection()
        for t in models.TABLES:
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                out[t] = -1
    return out


def backup_db(keep: int = 7) -> str | None:
    """Snapshot consistente de la BD (track record forward) a data/backups/.
    Usa VACUUM INTO (atómico). Conserva los últimos `keep`. Devuelve la ruta."""
    try:
        bdir = Path(DB_PATH).parent / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        dest = bdir / f"oscilion-{datetime.now():%Y%m%d}.db"
        if dest.exists():
            dest.unlink()
        with _lock:
            get_connection().execute("VACUUM INTO ?", (str(dest),))
        backups = sorted(bdir.glob("oscilion-*.db"))
        for old in backups[:-keep]:                 # podar antiguos
            old.unlink(missing_ok=True)
        log.info("backup BD -> %s", dest.name)
        return str(dest)
    except Exception:
        log.exception("Fallo backup_db")
        return None


def close() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
