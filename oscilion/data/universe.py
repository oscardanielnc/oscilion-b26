"""Universo de monedas operables + metadata (volumen, liquidez).

Descubre perps USDT líquidos en Binance, ordena por volumen en quote (USDT)
y persiste un snapshot a parquet. La selección fina (top-N, correlación) la
hará `risk/allocation.py` en fases posteriores; aquí solo el universo crudo.
"""
from __future__ import annotations

import logging

import pandas as pd

from config import DATA_DIR, config
from oscilion.data.fetch import get_exchange

log = logging.getLogger(__name__)

UNIVERSE_DIR = DATA_DIR / "universe"


def fetch_universe(*, quote: str = "USDT", min_quote_volume: float = 0.0) -> pd.DataFrame:
    """DataFrame de perps USDT lineales con su metadata de liquidez.

    Columnas: symbol, base, last, quote_volume, base_volume, active.
    Ordenado por quote_volume desc (proxy de liquidez).
    """
    ex = get_exchange()
    markets = ex.load_markets()
    tickers = ex.fetch_tickers()

    rows = []
    for sym, m in markets.items():
        if not (m.get("swap") and m.get("linear") and m.get("quote") == quote and m.get("active")):
            continue
        t = tickers.get(sym, {})
        qv = t.get("quoteVolume") or 0.0
        if qv < min_quote_volume:
            continue
        rows.append({
            "symbol": sym,
            "base": m.get("base"),
            "last": t.get("last"),
            "quote_volume": qv,
            "base_volume": t.get("baseVolume") or 0.0,
            "active": True,
        })

    df = pd.DataFrame(rows).sort_values("quote_volume", ascending=False).reset_index(drop=True)
    log.info("universo: %d perps %s linealmente activos", len(df), quote)
    return df


def save_universe(df: pd.DataFrame) -> None:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    path = UNIVERSE_DIR / f"{config.exchange}.parquet"
    df.to_parquet(path, index=False)
    log.info("universo guardado en %s", path)


def load_universe() -> pd.DataFrame:
    path = UNIVERSE_DIR / f"{config.exchange}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def top_symbols(n: int = 10, *, quote: str = "USDT") -> list[str]:
    """Top-N símbolos por liquidez (desde el snapshot guardado o en vivo)."""
    df = load_universe()
    if df.empty:
        df = fetch_universe(quote=quote)
    return df.head(n)["symbol"].tolist()
