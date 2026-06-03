"""Descarga de datos de mercado desde Binance (perps) vía ccxt.

Principios:
  • **Sin look-ahead**: se descarta SIEMPRE la última vela si aún no cerró.
    Solo entran velas con `open_ts + tf <= now`.
  • Paginación robusta: avanza por `since`, respeta rate limit, corta cuando
    el exchange deja de devolver datos nuevos.
  • Devuelve DataFrames tipados; la limpieza/persistencia vive en store.py.
"""
from __future__ import annotations

import logging
import re
import time

import pandas as pd

from config import config

log = logging.getLogger(__name__)

OHLCV_COLS = ["ts", "open", "high", "low", "close", "volume"]
_TF_UNITS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000, "w": 604_800_000}

_exchange = None  # singleton ccxt


def timeframe_to_ms(tf: str) -> int:
    """'15m'->900000, '1h'->3600000, '1d'->86400000."""
    m = re.fullmatch(r"(\d+)([mhdw])", tf.strip())
    if not m:
        raise ValueError(f"timeframe inválido: {tf!r}")
    return int(m.group(1)) * _TF_UNITS[m.group(2)]


def get_exchange():
    """Instancia ccxt única (rate-limit activado). Mercados cargados lazy."""
    global _exchange
    if _exchange is None:
        import ccxt

        klass = getattr(ccxt, config.exchange)
        _exchange = klass({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    return _exchange


def _now_ms() -> int:
    return get_exchange().milliseconds()


def fetch_ohlcv(
    sym: str, tf: str, *, since: int | None = None, until: int | None = None,
    page_limit: int = 1000, max_pages: int = 1000,
) -> pd.DataFrame:
    """OHLCV paginado, SIN la vela en curso. Columnas: ts,open,high,low,close,volume.

    `ts` = open time de la vela (epoch ms). `since`/`until` en epoch ms.
    """
    ex = get_exchange()
    tf_ms = timeframe_to_ms(tf)
    now = _now_ms()
    until = until or now
    # último cierre válido: open_ts + tf_ms <= now  =>  open_ts <= now - tf_ms
    last_closed_open = now - tf_ms

    rows: list[list] = []
    cursor = since
    for _ in range(max_pages):
        batch = ex.fetch_ohlcv(sym, timeframe=tf, since=cursor, limit=page_limit)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1][0]
        if len(batch) < page_limit or last_ts >= until:
            break
        cursor = last_ts + tf_ms  # siguiente página justo después
        time.sleep(ex.rateLimit / 1000)

    if not rows:
        return pd.DataFrame(columns=OHLCV_COLS)

    df = pd.DataFrame(rows, columns=OHLCV_COLS)
    # filtros: rango, dedupe y NO look-ahead (vela cerrada)
    df = df[(df["ts"] >= (since or 0)) & (df["ts"] <= until)]
    df = df[df["ts"] <= last_closed_open]
    df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    log.debug("fetch_ohlcv %s %s -> %d velas cerradas", sym, tf, len(df))
    return df


def fetch_funding(
    sym: str, *, since: int | None = None, until: int | None = None,
    page_limit: int = 1000, max_pages: int = 1000,
) -> pd.DataFrame:
    """Histórico de funding. Columnas: ts, funding_rate."""
    ex = get_exchange()
    if not ex.has.get("fetchFundingRateHistory"):
        log.warning("%s no soporta fetchFundingRateHistory", config.exchange)
        return pd.DataFrame(columns=["ts", "funding_rate"])

    until = until or _now_ms()
    rows: list[dict] = []
    cursor = since
    for _ in range(max_pages):
        batch = ex.fetch_funding_rate_history(sym, since=cursor, limit=page_limit)
        if not batch:
            break
        rows.extend(batch)
        last_ts = batch[-1]["timestamp"]
        if len(batch) < page_limit or last_ts >= until:
            break
        cursor = last_ts + 1
        time.sleep(ex.rateLimit / 1000)

    if not rows:
        return pd.DataFrame(columns=["ts", "funding_rate"])

    df = pd.DataFrame(
        {"ts": [r["timestamp"] for r in rows],
         "funding_rate": [r["fundingRate"] for r in rows]}
    )
    df = df[(df["ts"] >= (since or 0)) & (df["ts"] <= until)]
    df = df.dropna(subset=["ts"]).drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    log.debug("fetch_funding %s -> %d registros", sym, len(df))
    return df
