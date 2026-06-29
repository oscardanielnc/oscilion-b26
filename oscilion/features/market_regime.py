"""Régimen de MERCADO (beta del benchmark) — FUENTE ÚNICA (live + backtest).

Distinto de `features/regime.py` (rango|tendencia|caos POR SÍMBOLO). Aquí el
benchmark (BTC) define si el mercado base está alcista o bajista, para no operar
A FAVOR de la beta cuando va EN CONTRA del lado del trade.

La auditoría 06-29 mostró que los largos de continuación (vwap_anchor) sangran al
caer el mercado: 17/17 entradas LONG en alts bajando = trampas alcistas (−11R).
El cálculo vive aquí para que el monitor en vivo y el motor de backtest usen la
MISMA definición (igual que el modelo de costos es fuente única) y no diverjan.

Definición: alcista si close > EMA(`ema_len`) en el TF `tf_h` (resampleado del 1h).
Sin look-ahead: el régimen que aplica a una señal cerrada en T usa la barra de
régimen cuyo CIERRE ≤ T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from oscilion.backtest.resample import resample_ohlcv
from oscilion.features import indicators as ind

_H = 3_600_000


def regime_series(bars_1h: pd.DataFrame, tf_h: int, ema_len: int) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve (close_ts, bull) por barra de régimen.

    `close_ts` = epoch ms del CIERRE de cada barra del TF (open_ts + tf_h·1h).
    `bull` = close > EMA(ema_len). Arrays vacíos si no hay datos suficientes.
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
    """Régimen vigente en el instante `t_ms` (última barra cuyo cierre ≤ t_ms).
    None si no hay barra previa (sin datos / antes del primer cierre)."""
    if close_ts.size == 0:
        return None
    idx = int(np.searchsorted(close_ts, t_ms, side="right")) - 1
    if idx < 0:
        return None
    return bool(bull[idx])


def latest_bull(bars_1h: pd.DataFrame, tf_h: int, ema_len: int) -> bool | None:
    """Régimen MÁS RECIENTE (para el monitor en vivo). None si no hay datos."""
    close_ts, bull = regime_series(bars_1h, tf_h, ema_len)
    if close_ts.size == 0:
        return None
    return bool(bull[-1])
