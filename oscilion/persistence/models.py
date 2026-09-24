"""Database schema (ARCHITECTURE.md section 5).

Principle: **append-only and auditable**. Event rows are never overwritten or
deleted; only the aggregate/current-state tables (`forward_results`,
`ohlcv_status`, `monitor_state`, `calibration`) are upserted. Every event table
has `created_at` (epoch ms, insertion time) besides the event's logical `ts`.

The schema is versioned through `SCHEMA_VERSION`; migrations are idempotent
statements in `MIGRATIONS`.
"""
from __future__ import annotations

SCHEMA_VERSION = 6

TABLES: dict[str, str] = {
    # Market state per tick. Reserved: nothing writes it yet.
    "market_snapshots": """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,          -- snapshot epoch ms
            sym         TEXT    NOT NULL,
            price       REAL,
            ohlcv_ref   TEXT,                      -- ref/hash of the bars used
            indicators  TEXT,                      -- JSON: ATR, BB, ADX, ...
            created_at  INTEGER NOT NULL
        )
    """,
    # What the system "believed" at that moment.
    "predictions": """
        CREATE TABLE IF NOT EXISTS predictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            sym         TEXT    NOT NULL,
            score       REAL,                      -- conviction 0-100
            range_lo    REAL,
            range_hi    REAL,
            regime      TEXT,                      -- range | trend | chaos
            stop        REAL,
            tp          REAL,
            rr          REAL,                      -- expected risk/reward
            leverage    REAL,
            components  TEXT,                      -- JSON: score breakdown
            created_at  INTEGER NOT NULL
        )
    """,
    # What was decided and why.
    "decisions": """
        CREATE TABLE IF NOT EXISTS decisions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            sym         TEXT    NOT NULL,
            action      TEXT    NOT NULL,          -- enter | enter-observe | wait | no-trade
            reason      TEXT,
            prediction_id INTEGER,                 -- logical FK to predictions.id
            created_at  INTEGER NOT NULL
        )
    """,
    # Trades (dry-run / paper; live was never implemented).
    "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,          -- open time (epoch ms)
            sym         TEXT    NOT NULL,
            side        TEXT    NOT NULL,          -- long | short
            mode        TEXT    NOT NULL,          -- dry-run | paper | live
            entry       REAL,
            stop        REAL,
            tp          REAL,
            leverage    REAL,
            size        REAL,                      -- notional / contracts
            exit        REAL,
            exit_ts     INTEGER,
            pnl         REAL,
            fees        REAL,
            funding     REAL,
            status      TEXT    NOT NULL DEFAULT 'open',  -- open | closed
            strategy    TEXT,                      -- ema_trend_stack | orb_breakout | ...
            r_multiple  REAL,                      -- pnl in risk units (R)
            observe     INTEGER NOT NULL DEFAULT 0, -- 1 = forward test without capital (excluded from PnL)
            exit_reason TEXT,                      -- stop | tp | timeout | ...
            cost_audit  TEXT,                      -- JSON: R broken down (price/slip/fees/funding)
            created_at  INTEGER NOT NULL
        )
    """,
    # Forward validation per (sym, strategy, scope): the concise log that answers
    # keep/remove/fix/improve. Backtest vs forward (unseen data).
    "forward_results": """
        CREATE TABLE IF NOT EXISTS forward_results (
            sym         TEXT    NOT NULL,
            strategy    TEXT    NOT NULL,
            scope       TEXT    NOT NULL,          -- backtest | forward
            n           INTEGER NOT NULL DEFAULT 0,
            win_rate    REAL,
            exp_r       REAL,                      -- expectancy per trade in R
            sum_r       REAL,
            last_entry_ts INTEGER,
            updated_at  INTEGER NOT NULL,
            PRIMARY KEY (sym, strategy, scope)
        )
    """,
    # Configuration in use (reproducibility).
    "params": """
        CREATE TABLE IF NOT EXISTS params (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            version     TEXT    NOT NULL,
            json_params TEXT    NOT NULL,
            created_at  INTEGER NOT NULL
        )
    """,
    # Predicted score vs outcome (recomputable aggregate). Reserved: nothing writes it yet.
    "calibration": """
        CREATE TABLE IF NOT EXISTS calibration (
            bucket_score INTEGER PRIMARY KEY,      -- e.g. 0,10,...,90
            n            INTEGER NOT NULL DEFAULT 0,
            hits         INTEGER NOT NULL DEFAULT 0,
            ratio_real   REAL,
            updated_at   INTEGER NOT NULL
        )
    """,
    # Errors, restarts, alerts (operational audit).
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            level       TEXT    NOT NULL,          -- INFO | WARN | ERROR | CRITICAL
            module      TEXT,
            msg         TEXT    NOT NULL,
            extra       TEXT,                      -- optional JSON
            created_at  INTEGER NOT NULL
        )
    """,
    # Audit of the downloaded history. Upserted per (exchange, sym, tf, source):
    # the bars live in parquet, this is the summary.
    "ohlcv_status": """
        CREATE TABLE IF NOT EXISTS ohlcv_status (
            exchange    TEXT    NOT NULL,
            sym         TEXT    NOT NULL,
            tf          TEXT    NOT NULL,
            first_ts    INTEGER,
            last_ts     INTEGER,
            rows        INTEGER NOT NULL DEFAULT 0,
            gaps        INTEGER NOT NULL DEFAULT 0,
            dupes       INTEGER NOT NULL DEFAULT 0,
            source      TEXT,                      -- ohlcv | funding
            updated_at  INTEGER NOT NULL,
            PRIMARY KEY (exchange, sym, tf, source)
        )
    """,
    # Live monitor state (current state, upsert) to survive restarts: open virtual
    # positions + cursors per (sym|strategy). Without it, Restart=always would lose
    # positions and leave holes in the forward test.
    "monitor_state": """
        CREATE TABLE IF NOT EXISTS monitor_state (
            key         TEXT PRIMARY KEY,         -- "<sym>|<strategy>"
            state       TEXT NOT NULL,            -- JSON: position, last_sig_ts, last_15m_ts
            updated_at  INTEGER NOT NULL
        )
    """,
    # Concise snapshot of what the monitor sees each cycle, per (sym, strategy).
    # Append-only: records what the bot saw (state, direction, checklist progress)
    # even when there is no signal or trade. Written on a cadence (~hourly) and on
    # every change (alert).
    "series_snapshots": """
        CREATE TABLE IF NOT EXISTS series_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,          -- snapshot epoch ms
            sym         TEXT    NOT NULL,
            strategy    TEXT    NOT NULL,
            state       TEXT    NOT NULL,          -- waiting | active | in_trade
            direction   TEXT,                      -- long | short | neutral
            price       REAL,
            checklist_ok    INTEGER,               -- criteria met
            checklist_total INTEGER,               -- total criteria
            signal_active   INTEGER NOT NULL DEFAULT 0,  -- 0/1 candidate ready
            in_trade        INTEGER NOT NULL DEFAULT 0,  -- 0/1 position open
            created_at  INTEGER NOT NULL
        )
    """,
    # Internal schema version tracking.
    "schema_meta": """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """,
}

# Idempotent migrations (ALTER) for existing DBs. The "duplicate column" error is
# ignored when they were already applied.
MIGRATIONS: list[str] = [
    "ALTER TABLE trades ADD COLUMN strategy TEXT",
    "ALTER TABLE trades ADD COLUMN r_multiple REAL",
    # v6: observe gate + exit cost audit (FORWARD_REVIEW #1/#3)
    "ALTER TABLE trades ADD COLUMN observe INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE trades ADD COLUMN exit_reason TEXT",
    "ALTER TABLE trades ADD COLUMN cost_audit TEXT",
]

# Indexes for frequent queries (dashboard).
INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS ix_snapshots_sym_ts ON market_snapshots(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_predictions_sym_ts ON predictions(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_decisions_sym_ts ON decisions(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_trades_sym_status ON trades(sym, status)",
    "CREATE INDEX IF NOT EXISTS ix_events_level_ts ON events(level, ts)",
    "CREATE INDEX IF NOT EXISTS ix_series_snap_ts ON series_snapshots(ts)",
    "CREATE INDEX IF NOT EXISTS ix_series_snap_sym_strat_ts ON series_snapshots(sym, strategy, ts)",
]
