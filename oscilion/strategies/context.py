"""Construcción del contexto multi-TF para evaluar estrategias.

Misma función para backtest (historia completa) y live (últimas velas cerradas):
lee del store, resamplea 1h→TF de señal y auxiliares, precomputa indicadores.
Sin look-ahead: resample descarta el bucket incompleto.
"""
from __future__ import annotations

import pandas as pd

from oscilion.backtest.resample import resample_ohlcv
from oscilion.data import store
from oscilion.features import indicators as ind
from oscilion.strategies import library as S


def tf_arrays(df: pd.DataFrame) -> S.TFArrays:
    c = df["close"]
    return S.TFArrays(
        ts=df["ts"].to_numpy(), open=df["open"].to_numpy(), high=df["high"].to_numpy(),
        low=df["low"].to_numpy(), close=c.to_numpy(), volume=df["volume"].to_numpy(),
        ema9=ind.ema(c, 9).to_numpy(), ema21=ind.ema(c, 21).to_numpy(),
        ema50=ind.ema(c, 50).to_numpy(), atr=ind.atr(df, 14).to_numpy(),
        rsi=ind.rsi(c, 14).to_numpy(), vwap=ind.rolling_vwap(df, 24).to_numpy(),
    )


def build_ctx(sym: str, strategy: str, *, tail_1h: int | None = None) -> S.Ctx | None:
    """Contexto para `sym`+`strategy`. `tail_1h` limita las velas 1h cargadas
    (None=todo, para backtest; p.ej. 1200 para live = eficiente)."""
    spec = S.REGISTRY[strategy]
    h1 = store.load_bars(sym, "1h")
    if h1.empty or len(h1) < 300:
        return None
    if tail_1h is not None and len(h1) > tail_1h:
        h1 = h1.tail(tail_1h).reset_index(drop=True)
    sig_h = spec["signal_tf_h"]
    sig_df = resample_ohlcv(h1, sig_h) if sig_h > 1 else h1
    if len(sig_df) < 80:
        return None
    ctx = S.Ctx(sig=tf_arrays(sig_df), sig_tf_h=sig_h)
    for h in spec.get("aux_tfs", []):
        aux_df = h1 if h == 1 else resample_ohlcv(h1, h)
        ctx.aux[h] = tf_arrays(aux_df)
    return ctx
