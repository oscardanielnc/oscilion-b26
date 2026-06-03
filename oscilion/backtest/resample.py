"""Resampleo causal de OHLCV a timeframes superiores (Fase de pruebas R1).

1h → 2h/4h por agregación estándar alineada a fronteras UTC. Se descarta el
último bucket si está incompleto (no inventa una vela aún no cerrada → sin
look-ahead). `ts` = open time del bucket (epoch ms).
"""
from __future__ import annotations

import pandas as pd

_H = 3_600_000


def resample_ohlcv(df: pd.DataFrame, hours: int) -> pd.DataFrame:
    """Agrega un df 1h (ts,open,high,low,close,volume) a `hours`-horas."""
    if df.empty:
        return df.copy()
    factor = hours * _H
    d = df.copy()
    d["bucket"] = (d["ts"] // factor) * factor
    g = d.groupby("bucket", sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
                _n=("ts", "size")).reset_index()
    out = out[out["_n"] == hours]               # solo buckets completos (sin look-ahead)
    out = out.rename(columns={"bucket": "ts"}).drop(columns="_n")
    return out[["ts", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
