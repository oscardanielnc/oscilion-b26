"""Tradable universe + metadata (volume, liquidity).

Discovers liquid USDT perpetuals on Binance, sorts them by quote volume (USDT)
and saves a parquet snapshot. Only the raw universe; selection happens elsewhere.
"""
from __future__ import annotations

import logging

import pandas as pd

from config import DATA_DIR, config
from oscilion.data.fetch import get_exchange

log = logging.getLogger(__name__)

UNIVERSE_DIR = DATA_DIR / "universe"


def fetch_universe(*, quote: str = "USDT", min_quote_volume: float = 0.0) -> pd.DataFrame:
    """DataFrame of linear USDT perpetuals with liquidity metadata.

    Columns: symbol, base, last, quote_volume, base_volume, active.
    Sorted by quote_volume desc (liquidity proxy).
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
    log.info("universe: %d active linear %s perps", len(df), quote)
    return df


def save_universe(df: pd.DataFrame) -> None:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    path = UNIVERSE_DIR / f"{config.exchange}.parquet"
    df.to_parquet(path, index=False)
    log.info("universe saved to %s", path)
