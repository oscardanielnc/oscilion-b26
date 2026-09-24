"""Causal OHLCV resampling to higher timeframes.

1h -> 2h/4h by standard aggregation aligned to UTC boundaries. Incomplete buckets
are dropped (no invented, unclosed candle -> no look-ahead). `ts` = bucket open
time (epoch ms).
"""
from __future__ import annotations

import pandas as pd

_H = 3_600_000


def resample_ohlcv(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    """Aggregate a 1h df (ts,open,high,low,close,volume) into `hours`-hour bars."""
    if df.empty:
        return df.copy()
    factor = hours * _H
    d = df.copy()
    d["bucket"] = (d["ts"] // factor) * factor
    g = d.groupby("bucket", sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
                _n=("ts", "size")).reset_index()
    out = out[out["_n"] == hours]               # complete buckets only (no look-ahead)
    out = out.rename(columns={"bucket": "ts"}).drop(columns="_n")
    return out[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
