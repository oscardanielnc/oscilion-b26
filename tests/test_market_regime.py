"""Market regime (benchmark beta): single source for live and backtest (06-29).
Checks the close > EMA classification and that `bull_at` never looks ahead.
"""
import numpy as np
import pandas as pd

from oscilion.features import market_regime as mr

_H = 3_600_000


def _bars(closes, tf_h=1):
    n = len(closes)
    ts = np.arange(n) * tf_h * _H
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"ts": ts, "open": c, "high": c, "low": c,
                         "close": c, "volume": np.ones(n)})


def test_regime_bull_vs_bear():
    # long rising ramp -> close above its EMA -> bullish at the end
    up = _bars(list(range(1, 200)))
    assert mr.latest_bull(up, tf_h=1, ema_len=50) is True
    # falling ramp -> bearish at the end
    down = _bars(list(range(200, 1, -1)))
    assert mr.latest_bull(down, tf_h=1, ema_len=50) is False


def test_regime_without_data_is_none():
    assert mr.latest_bull(_bars([1, 2, 3]), tf_h=1, ema_len=50) is None
    assert mr.bull_at(np.array([]), np.array([], dtype=bool), 123) is None


def test_bull_at_no_lookahead():
    closes = list(range(1, 120))
    close_ts, bull = mr.regime_series(_bars(closes), tf_h=1, ema_len=50)
    # before the first regime bar closes -> None (does not invent the past)
    assert mr.bull_at(close_ts, bull, int(close_ts[0]) - 1) is None
    # at t = the exact close of a bar -> uses THAT bar (close <= t), not the next one
    idx = 70
    assert mr.bull_at(close_ts, bull, int(close_ts[idx])) == bool(bull[idx])
    # one instant before close idx -> uses the previous bar
    assert mr.bull_at(close_ts, bull, int(close_ts[idx]) - 1) == bool(bull[idx - 1])
