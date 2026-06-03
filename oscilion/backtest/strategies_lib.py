"""Estrategias portadas del proyecto BTC/Sentinel (Fase de pruebas R2).

Funciones puras de señal: dado un contexto con arrays precomputados por TF y un
índice de barra de señal `i`, devuelven un candidato {side, entry_ref, stop, tp}
usando SOLO información ≤ cierre de la barra i (sin look-ahead).

Fieles a playbook/strategies/*.yaml del proyecto BTC, parametrizadas para barrido.
NO se importan en el sistema live aún — solo validación.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

_H = 3_600_000


@dataclass
class TFArrays:
    ts: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    ema9: np.ndarray
    ema21: np.ndarray
    ema50: np.ndarray
    atr: np.ndarray
    rsi: np.ndarray


@dataclass
class Ctx:
    sig: TFArrays          # TF de señal (2h o 4h)
    sig_tf_h: int          # horas del TF de señal
    h1: TFArrays | None = None      # 1h (para gate de frescura de EMA_STACK)
    h1_ts_to_idx: dict = field(default_factory=dict)


# ----------------------------- MOMENTUM PULLBACK -----------------------------
def momentum_pullback(ctx: Ctx, i: int, p: dict) -> dict | None:
    s = ctx.sig
    lb = p.get("lookback", 12)
    atr_n = 14
    if i < lb + atr_n + 1:
        return None
    atr = s.atr[i]
    if not np.isfinite(atr) or atr <= 0:
        return None

    # mayor movimiento close-to-close en las últimas `lb` velas
    diffs = s.close[i - lb + 1: i + 1] - s.close[i - lb: i]
    if diffs.size == 0:
        return None
    j_rel = int(np.argmax(np.abs(diffs)))
    body = abs(diffs[j_rel])
    if body < p.get("impulse_atr_min", 0.8) * atr:
        return None
    direction = 1 if diffs[j_rel] > 0 else -1
    j = i - lb + 1 + j_rel                      # índice de la vela de impulso (cierre)

    seg = s.close[j: i + 1]
    if seg.size < 2:
        return None
    if direction > 0:
        extreme = float(np.min(seg))
        retrace = (s.close[j] - extreme) / body
    else:
        extreme = float(np.max(seg))
        retrace = (extreme - s.close[j]) / body
    if not (p.get("pullback_min", 0.10) <= retrace <= p.get("pullback_max", 0.80)):
        return None

    side = "long" if direction > 0 else "short"
    if p.get("long_only", True) and side == "short":
        return None
    # gate de frescura: EMA9/21 NO alineado aún con la dirección
    if p.get("fresh_gate", True):
        aligned = (s.ema9[i] > s.ema21[i]) if side == "long" else (s.ema9[i] < s.ema21[i])
        if aligned:
            return None
    if p.get("require_bounce", False):
        if (side == "long" and s.close[i] <= s.close[i - 1]) or \
           (side == "short" and s.close[i] >= s.close[i - 1]):
            return None

    entry = float(s.close[i])
    buf = p.get("sl_atr_buf", 0.5) * atr
    stop = extreme - buf if side == "long" else extreme + buf
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    tp = entry + p.get("tp_r", 2.0) * risk if side == "long" else entry - p.get("tp_r", 2.0) * risk
    return {"side": side, "entry_ref": entry, "stop": float(stop), "tp": float(tp)}


# ------------------------------ EMA TREND STACK ------------------------------
def ema_trend_stack(ctx: Ctx, i: int, p: dict) -> dict | None:
    s = ctx.sig
    if i < 55 or not np.isfinite(s.ema50[i]) or not np.isfinite(s.atr[i]):
        return None
    side = "long"  # LONG-only (sesgo alcista BTC; SHORT destruía capital)
    # C1: stack alineado
    if not (s.ema9[i] > s.ema21[i] > s.ema50[i]):
        return None
    # C2: precio sobre EMA50
    if not (s.close[i] > s.ema50[i]):
        return None
    # C5: pullback reciente a EMA21 + por encima ahora
    lb = p.get("pullback_lookback", 3)
    margin = p.get("pullback_margin", 0.0015)
    recent_low = float(np.min(s.low[i - lb + 1: i + 1]))
    if not (recent_low <= s.ema21[i] * (1 + margin) and s.close[i] > s.ema21[i]):
        return None
    # C4 opcional: RSI saludable
    if p.get("rsi_filter", False) and np.isfinite(s.rsi[i]):
        if not (40 <= s.rsi[i] <= 65):
            return None
    # Gate de frescura C3: 1h NO alineado alcista aún
    if p.get("fresh_gate", True) and ctx.h1 is not None:
        T = int(s.ts[i]) + ctx.sig_tf_h * _H            # close time de la señal
        h1_open = T - _H                                # 1h que cerró en T
        idx = ctx.h1_ts_to_idx.get(h1_open)
        if idx is not None:
            if ctx.h1.ema9[idx] > ctx.h1.ema21[idx]:    # 1h ya alcista → tardío
                return None
    # Session filter: cierres en UTC {8,12,16,20} (Lima 3,7,11,15)
    if p.get("session_filter", True):
        T = int(s.ts[i]) + ctx.sig_tf_h * _H
        hour_utc = (T // _H) % 24
        if hour_utc not in (8, 12, 16, 20):
            return None

    entry = float(s.close[i])
    stop = entry - p.get("atr_mult_sl", 1.0) * s.atr[i]
    risk = entry - stop
    if risk <= 0:
        return None
    tp = entry + p.get("tp_r", 2.0) * risk
    return {"side": side, "entry_ref": entry, "stop": float(stop), "tp": float(tp)}


REGISTRY = {
    "momentum_pullback": {"fn": momentum_pullback, "signal_tf_h": 2, "needs_h1": False},
    "ema_trend_stack": {"fn": ema_trend_stack, "signal_tf_h": 4, "needs_h1": True},
}
