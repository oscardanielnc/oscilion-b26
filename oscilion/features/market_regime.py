"""MARKET regime (benchmark beta): SINGLE SOURCE for live and backtest.

Different from `features/regime.py` (range|trend|chaos PER SYMBOL). Here the
benchmark (BTC) decides whether the base market is bullish or bearish, so a
trade is not taken while the market beta runs AGAINST its side.

Audit 06-29 showed that continuation longs (vwap_anchor) bleed when the market
falls: 17/17 LONG entries on falling alts were bull traps (-11R). The computation
lives here so the live monitor and the backtest engine use the SAME definition
(just like the cost model is a single source) and cannot diverge.

Definition: bullish if close > EMA(`ema_len`) on the `tf_h` TF (resampled from 1h).
No look-ahead: the regime applied to a signal closed at T uses the regime bar
whose CLOSE <= T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from oscilion.backtest.resample import resample_ohlcv
from oscilion.features import indicators as ind

_H = 3_600_000


def regime_series(bars_1h: pd.DataFrame, tf_h: int, ema_len: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (close_ts, bull) per regime bar.

    `close_ts` = epoch ms of each TF bar's CLOSE (open_ts + tf_h * 1h).
    `bull` = close > EMA(ema_len). Empty arrays if there is not enough data.
    """
    if bars_1h is None or bars_1h.empty or len(bars_1h) < 60:
        return np.array([]), np.array([], dtype=bool)
    df = resample_ohlcv(bars_1h, tf_h) if tf_h > 1 else bars_1h
    if len(df) < ema_len + 2:
        return np.array([]), np.array([], dtype=bool)
    ema = ind.ema(df["close"], ema_len).to_numpy()
    close = df["close"].to_numpy()
    close_ts = df["ts"].to_numpy() + tf_h * _H
    return close_ts, close > ema


def bull_at(close_ts: np.ndarray, bull: np.ndarray, t_ms: int) -> bool | None:
    """Regime in force at `t_ms` (last bar whose close <= t_ms).
    None if there is no prior bar (no data / before the first close)."""
    if close_ts.size == 0:
        return None
    idx = int(np.searchsorted(close_ts, t_ms, side="right")) - 1
    if idx < 0:
        return None
    return bool(bull[idx])


def latest_bull(bars_1h: pd.DataFrame, tf_h: int, ema_len: int) -> bool | None:
    """MOST RECENT regime (for the live monitor). None if there is no data."""
    close_ts, bull = regime_series(bars_1h, tf_h, ema_len)
    if close_ts.size == 0:
        return None
    return bool(bull[-1])
