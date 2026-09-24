"""Technical indicators.

Every function works on CLOSED candles (DataFrame with columns
ts,open,high,low,close,volume) and returns Series aligned with the df index.
No look-ahead: each value at t only uses information <= t. `min_periods`
keeps NaN until the window is full (no invented values).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing (RMA): EMA with alpha = 1/n."""
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return _wilder(true_range(df), n)


def atr_pct(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """ATR relative to price (% volatility per bar)."""
    return atr(df, n) / df["close"]


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = _wilder(gain, n) / _wilder(loss, n)
    return 100 - 100 / (1 + rs)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    upper = mid + k * sd
    lower = mid - k * sd
    width = upper - lower
    return pd.DataFrame({
        "bb_mid": mid, "bb_upper": upper, "bb_lower": lower,
        "bb_pctb": (close - lower) / width,
        "bb_bandwidth": width / mid,
    })


def rolling_vwap(df: pd.DataFrame, n: int = 24) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = (tp * df["volume"]).rolling(n).sum()
    vv = df["volume"].rolling(n).sum()
    return pv / vv


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """ADX + directional indices (Wilder). High ADX => strong trend."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = true_range(df)
    atr_ = _wilder(tr, n)
    plus_di = 100 * _wilder(pd.Series(plus_dm, index=df.index), n) / atr_
    minus_di = 100 * _wilder(pd.Series(minus_dm, index=df.index), n) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"adx": _wilder(dx, n), "plus_di": plus_di, "minus_di": minus_di})
