"""SQLite connection, idempotent migrations and the append-only write API.

- WAL + a shared thread-safe connection (lock), so the orchestrator and the API
  can read/write without stepping on each other.
- Event tables are only written through `log_*` (INSERT). There is no
  update/delete of events: the audit trail is inviolable. Only aggregate and
  current-state tables are upserted.
- Every write is defensive: a DB failure must NOT bring the tick down (it
  returns None and leaves a trace in the logger). Resilience comes first.
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
    """Single lazy connection, with WAL and foreign keys enabled."""
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
                # API and orchestrator are two processes on the same DB: wait
                # instead of failing with SQLITE_BUSY when a read and write collide.
                _conn.execute("PRAGMA busy_timeout=5000")
    return _conn


def init_db() -> None:
    """Create tables and indexes (idempotent) and record the schema version."""
    conn = get_connection()
    with _lock:
        for ddl in models.TABLES.values():
            conn.execute(ddl)
        for alter in getattr(models, "MIGRATIONS", []):
            try:
                conn.execute(alter)
            except Exception:
                pass  # column already exists (idempotent migration)
        for idx in models.INDEXES:
            conn.execute(idx)
        conn.execute(
            "INSERT INTO schema_meta(key, value, updated_at) VALUES('schema_version', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (str(models.SCHEMA_VERSION), _now_ms()),
        )
    log.info("DB ready at %s (schema v%d)", DB_PATH, models.SCHEMA_VERSION)


def _insert(table: str, data: dict[str, Any]) -> Optional[int]:
    """Generic defensive INSERT with retries. Returns the row id or None.

    Retries on 'database is locked' (cross-process contention) on top of
    PRAGMA busy_timeout, so critical rows (trades/alerts) are not lost.
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
            log.error("INSERT %s failed (locked) after retries: %s", table, e)
            return None
        except Exception:  # a persistence failure must never bring the tick down
            log.exception("Insert into %s failed", table)
            return None
    return None


def _jdump(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    return json.dumps(obj, default=str, separators=(",", ":"))


# -------------------------- append-only API --------------------------

def log_series_snapshot(
    sym: str, strategy: str, *, state: str, direction: str | None = None,
    price: float | None = None, checklist_ok: int | None = None,
    checklist_total: int | None = None, signal_active: bool = False,
    in_trade: bool = False, ts: int | None = None,
) -> Optional[int]:
    """Concise per-cycle snapshot of what the monitor sees (append-only)."""
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
    """Closed PnL of trades WITH CAPITAL (observe=0) since `since_ms`.
    Used by the daily brake. Returns 0.0 on failure: a DB error must not trigger
    the brake (the error circuit breaker already covers that case)."""
    try:
        with _lock:
            row = get_connection().execute(
                "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status='closed'"
                " AND COALESCE(observe, 0)=0 AND exit_ts >= ?", (since_ms,),
            ).fetchone()
        return float(row[0] or 0.0)
    except Exception:
        log.exception("capital_pnl_since failed")
        return 0.0


def get_forward_result(sym: str, strategy: str, scope: str) -> Optional[dict]:
    """Persisted stats of the honest engine for a scope ('backtest' | 'forward').
    None if there is no snapshot yet (forward.refresh has not run)."""
    try:
        with _lock:
            row = get_connection().execute(
                "SELECT n, win_rate, exp_r, sum_r FROM forward_results"
                " WHERE sym=? AND strategy=? AND scope=?",
                (sym, strategy, scope),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        log.exception("get_forward_result failed %s %s %s", sym, strategy, scope)
        return None


def get_forward_backtest(sym: str, strategy: str) -> Optional[dict]:
    """LOCAL (OOS) backtest stats for the gate. None means the gate blocks."""
    return get_forward_result(sym, strategy, "backtest")


def real_forward_stats(sym: str, strategy: str, since_ms: int | None = None) -> Optional[dict]:
    """Stats of the REAL book (trades table, capital + observe) for the adaptive gate.

    Audit 07-02: the 'forward' scope in forward_results is a SIMULATION of the
    engine with the current rules over history. It can diverge from the book
    (XAU momentum: +1.35 simulated vs -2.47R real) because it simulates entries
    the monitor never took (vetoes, portfolio limits, downtime) and misses others.
    Kill-switch and graduation must decide on what REALLY happened.

    Includes observe trades (they are exactly the graduation evidence; r_multiple
    is comparable). `since_ms` limits the window to the current rules era
    (config.gate_real_fw_from_ms) so a combo is not killed for losses from an
    earlier engine version.
    None if there are no closed trades (the gate falls back to the backtest) or
    on DB failure.
    """
    from config import config
    since = config.gate_real_fw_from_ms if since_ms is None else since_ms
    try:
        with _lock:
            row = get_connection().execute(
                "SELECT COUNT(*) n, AVG(r_multiple) exp_r, SUM(r_multiple) sum_r,"
                " AVG(r_multiple > 0) win_rate FROM trades"
                " WHERE sym=? AND strategy=? AND status='closed'"
                " AND r_multiple IS NOT NULL AND ts >= ?",
                (sym, strategy, since),
            ).fetchone()
        if not row or not row["n"]:
            return None
        return dict(row)
    except Exception:
        log.exception("real_forward_stats failed %s %s", sym, strategy)
        return None


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
    """Auditable summary of the history per (exchange, sym, tf, source)."""
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
        log.exception("ohlcv_status upsert failed %s %s %s", sym, tf, source)


def upsert_forward_result(sym: str, strategy: str, scope: str, *, n: int,
                          win_rate: float | None, exp_r: float | None,
                          sum_r: float | None, last_entry_ts: int | None) -> None:
    """Concise validation snapshot (backtest vs forward) per sym x strategy."""
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
        log.exception("upsert_forward_result failed %s %s %s", sym, strategy, scope)


def save_monitor_state(key: str, state: dict) -> None:
    """Persist the state of one monitor series (upsert)."""
    try:
        with _lock:
            get_connection().execute(
                "INSERT INTO monitor_state (key, state, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
                (key, _jdump(state) or "{}", _now_ms()),
            )
    except Exception:
        log.exception("save_monitor_state failed %s", key)


def load_monitor_states() -> dict[str, dict]:
    """Rehydrate the monitor state after a restart."""
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
        log.exception("load_monitor_states failed")
    return out


def counts() -> dict[str, int]:
    """Row count per table (for the API /status endpoint and diagnostics)."""
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
    """Consistent DB snapshot (forward track record) into data/backups/.
    Uses VACUUM INTO (atomic). Keeps the last `keep`. Returns the path."""
    try:
        bdir = Path(DB_PATH).parent / "backups"
        bdir.mkdir(parents=True, exist_ok=True)
        dest = bdir / f"oscilion-{datetime.now():%Y%m%d}.db"
        if dest.exists():
            dest.unlink()
        with _lock:
            get_connection().execute("VACUUM INTO ?", (str(dest),))
        backups = sorted(bdir.glob("oscilion-*.db"))
        for old in backups[:-keep]:
            old.unlink(missing_ok=True)
        log.info("DB backup -> %s", dest.name)
        return str(dest)
    except Exception:
        log.exception("backup_db failed")
        return None


def close() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
