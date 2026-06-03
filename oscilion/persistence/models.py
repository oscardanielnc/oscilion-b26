"""Esquema de la base de datos (ARCHITECTURE.md §5).

Principio: **append-only y auditable**. Nunca se sobreescribe ni se borra
(salvo `calibration`, que es un agregado recomputable). Cada tabla lleva
`created_at` (epoch ms, hora de inserción) además del `ts` lógico del evento.

El esquema se versiona vía `SCHEMA_VERSION`; las migraciones futuras se
añadirán como sentencias idempotentes.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

# Cada entrada: CREATE TABLE IF NOT EXISTS idempotente.
TABLES: dict[str, str] = {
    # Estado del mercado en cada tick.
    "market_snapshots": """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,          -- epoch ms del snapshot
            sym         TEXT    NOT NULL,
            price       REAL,
            ohlcv_ref   TEXT,                      -- ref/hash a las barras usadas
            indicators  TEXT,                      -- JSON: ATR, BB, ADX, ...
            created_at  INTEGER NOT NULL
        )
    """,
    # Lo que el sistema "creía" en ese instante.
    "predictions": """
        CREATE TABLE IF NOT EXISTS predictions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            sym         TEXT    NOT NULL,
            score       REAL,                      -- convicción 0-100
            range_lo    REAL,
            range_hi    REAL,
            regime      TEXT,                      -- range | trend | chaos
            stop        REAL,
            tp          REAL,
            rr          REAL,                      -- risk/reward esperado
            leverage    REAL,
            components  TEXT,                      -- JSON: desglose del score
            created_at  INTEGER NOT NULL
        )
    """,
    # Qué se decidió y por qué.
    "decisions": """
        CREATE TABLE IF NOT EXISTS decisions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            sym         TEXT    NOT NULL,
            action      TEXT    NOT NULL,          -- entrar | esperar | no-operar | salir
            reason      TEXT,
            prediction_id INTEGER,                 -- FK lógica a predictions.id
            created_at  INTEGER NOT NULL
        )
    """,
    # Operaciones reales / paper.
    "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,          -- apertura (epoch ms)
            sym         TEXT    NOT NULL,
            side        TEXT    NOT NULL,          -- long | short
            mode        TEXT    NOT NULL,          -- dry-run | paper | live
            entry       REAL,
            stop        REAL,
            tp          REAL,
            leverage    REAL,
            size        REAL,                      -- notional / contratos
            exit        REAL,
            exit_ts     INTEGER,
            pnl         REAL,
            fees        REAL,
            funding     REAL,
            status      TEXT    NOT NULL DEFAULT 'open',  -- open | closed
            created_at  INTEGER NOT NULL
        )
    """,
    # Configuración usada (reproducibilidad).
    "params": """
        CREATE TABLE IF NOT EXISTS params (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            version     TEXT    NOT NULL,
            json_params TEXT    NOT NULL,
            created_at  INTEGER NOT NULL
        )
    """,
    # Score predicho vs resultado (agregado recomputable).
    "calibration": """
        CREATE TABLE IF NOT EXISTS calibration (
            bucket_score INTEGER PRIMARY KEY,      -- p.ej. 0,10,...,90
            n            INTEGER NOT NULL DEFAULT 0,
            hits         INTEGER NOT NULL DEFAULT 0,
            ratio_real   REAL,
            updated_at   INTEGER NOT NULL
        )
    """,
    # Errores, reinicios, alertas (auditoría operativa).
    "events": """
        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          INTEGER NOT NULL,
            level       TEXT    NOT NULL,          -- INFO | WARN | ERROR | CRITICAL
            module      TEXT,
            msg         TEXT    NOT NULL,
            extra       TEXT,                      -- JSON opcional
            created_at  INTEGER NOT NULL
        )
    """,
    # Estado/auditoría del histórico descargado (Fase 2). Agregado upsert
    # por (exchange, sym, tf): el detalle vive en parquet; aquí el resumen.
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
    # Control interno de versión de esquema.
    "schema_meta": """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """,
}

# Índices para consultas frecuentes (frontend / calibración).
INDEXES: list[str] = [
    "CREATE INDEX IF NOT EXISTS ix_snapshots_sym_ts ON market_snapshots(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_predictions_sym_ts ON predictions(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_decisions_sym_ts ON decisions(sym, ts)",
    "CREATE INDEX IF NOT EXISTS ix_trades_sym_status ON trades(sym, status)",
    "CREATE INDEX IF NOT EXISTS ix_events_level_ts ON events(level, ts)",
]
