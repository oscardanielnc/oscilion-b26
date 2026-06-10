"""Estrategias portadas del proyecto BTC/Sentinel (Fase de pruebas R2/R3).

Funciones puras de señal: dado un contexto con arrays precomputados por TF y un
índice de barra de señal `i`, devuelven un candidato {side, entry_ref, stop, tp}
usando SOLO información ≤ cierre de la barra i (sin look-ahead).

Multi-TF: `ctx.sig` es el TF de señal; `ctx.aux[h]` son otros TF (1h/4h) ya
cerrados; `aux_at(ctx,h,T)` da el índice del aux más reciente cerrado ≤ T.
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
    volume: np.ndarray
    ema9: np.ndarray
    ema21: np.ndarray
    ema50: np.ndarray
    atr: np.ndarray
    rsi: np.ndarray
    vwap: np.ndarray


@dataclass
class Ctx:
    sig: TFArrays
    sig_tf_h: int
    aux: dict = field(default_factory=dict)        # hours -> TFArrays


def tp_barrier(tp: float | None, side: str) -> float:
    """Nivel de TP para chequeos hi/lo. tp=None = runner (sin TP): devuelve ±inf,
    que NUNCA dispara — nada de centinelas 1e18 que contaminan sizing/logs."""
    if tp is None:
        return float("inf") if side == "long" else float("-inf")
    return float(tp)


def aux_at(ctx: Ctx, h: int, T: int) -> int | None:
    """Índice del bar de TF `h` ya CERRADO en el instante T (close ≤ T)."""
    a = ctx.aux.get(h)
    if a is None:
        return None
    pos = int(np.searchsorted(a.ts, T - h * _H, side="right")) - 1
    return pos if pos >= 0 else None


# ----------------------------- MOMENTUM PULLBACK -----------------------------
def momentum_pullback(ctx: Ctx, i: int, p: dict) -> dict | None:
    s = ctx.sig
    lb = p.get("lookback", 12)
    if i < lb + 15:
        return None
    atr = s.atr[i]
    if not np.isfinite(atr) or atr <= 0:
        return None
    diffs = s.close[i - lb + 1: i + 1] - s.close[i - lb: i]
    if diffs.size == 0:
        return None
    j_rel = int(np.argmax(np.abs(diffs)))
    body = abs(diffs[j_rel])
    if body < p.get("impulse_atr_min", 0.8) * atr:
        return None
    direction = 1 if diffs[j_rel] > 0 else -1
    j = i - lb + 1 + j_rel
    seg = s.close[j: i + 1]
    if seg.size < 2:
        return None
    if direction > 0:
        extreme = float(np.min(seg)); retrace = (s.close[j] - extreme) / body
    else:
        extreme = float(np.max(seg)); retrace = (extreme - s.close[j]) / body
    if not (p.get("pullback_min", 0.10) <= retrace <= p.get("pullback_max", 0.80)):
        return None
    side = "long" if direction > 0 else "short"
    if p.get("long_only", True) and side == "short":
        return None
    if p.get("fresh_gate", True):
        aligned = (s.ema9[i] > s.ema21[i]) if side == "long" else (s.ema9[i] < s.ema21[i])
        if aligned:
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
    side = "long"
    if not (s.ema9[i] > s.ema21[i] > s.ema50[i]):
        return None
    if not (s.close[i] > s.ema50[i]):
        return None
    lb = p.get("pullback_lookback", 3)
    margin = p.get("pullback_margin", 0.0015)
    recent_low = float(np.min(s.low[i - lb + 1: i + 1]))
    if not (recent_low <= s.ema21[i] * (1 + margin) and s.close[i] > s.ema21[i]):
        return None
    if p.get("rsi_filter", False) and np.isfinite(s.rsi[i]):
        if not (40 <= s.rsi[i] <= 65):
            return None
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    if p.get("fresh_gate", True):
        k = aux_at(ctx, 1, T)
        if k is not None and ctx.aux[1].ema9[k] > ctx.aux[1].ema21[k]:
            return None
    if p.get("session_filter", True):
        if (T // _H) % 24 not in (8, 12, 16, 20):
            return None
    entry = float(s.close[i])
    stop = entry - p.get("atr_mult_sl", 1.0) * s.atr[i]
    risk = entry - stop
    if risk <= 0:
        return None
    return {"side": side, "entry_ref": entry, "stop": float(stop),
            "tp": float(entry + p.get("tp_r", 2.0) * risk)}


# ------------------------------- ORB BREAKOUT --------------------------------
def orb_breakout(ctx: Ctx, i: int, p: dict) -> dict | None:
    s = ctx.sig                                  # 1h
    rng = p.get("range_bars", 6)
    if i < rng + 2 or not np.isfinite(s.atr[i]) or s.atr[i] <= 0:
        return None
    hi = float(np.max(s.high[i - rng: i]))       # rango de las `rng` velas previas
    lo = float(np.min(s.low[i - rng: i]))
    price = float(s.close[i])
    mid = (hi + lo) / 2
    if mid <= 0 or (hi - lo) / mid > p.get("range_max_pct", 0.015):   # C2 rango estrecho
        return None
    if price > hi:
        side = "long"
    elif price < lo:
        side = "short"
    else:
        return None
    if p.get("long_only", False) and side == "short":
        return None
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    # C3: EMA50 4h alineado
    k = aux_at(ctx, 4, T)
    if k is None or not np.isfinite(ctx.aux[4].ema50[k]):
        return None
    if side == "long" and not (price > ctx.aux[4].ema50[k]):
        return None
    if side == "short" and not (price < ctx.aux[4].ema50[k]):
        return None
    # O1 gate de frescura (EMA9/21 1h aún no alineado con la dirección)
    if p.get("fresh_gate", True):
        aligned = (s.ema9[i] > s.ema21[i]) if side == "long" else (s.ema9[i] < s.ema21[i])
        if aligned:
            return None
    # session EU/NY: cierre UTC en [8,21)
    if p.get("session_filter", True):
        if not (8 <= (T // _H) % 24 < 21):
            return None
    atr = s.atr[i]
    if side == "long":
        stop = lo - p.get("sl_atr_buf", 0.5) * atr
        stop = min(stop, price - 1.0 * atr)      # mínimo 1xATR de riesgo
    else:
        stop = hi + p.get("sl_atr_buf", 0.5) * atr
        stop = max(stop, price + 1.0 * atr)
    risk = abs(price - stop)
    if risk <= 0:
        return None
    tp_r = p.get("tp_r", 4.0)
    if tp_r <= 0:
        tp = None                                 # runner: sin TP (corre hasta SL/timeout)
    else:
        tp = float(price + tp_r * risk if side == "long" else price - tp_r * risk)
    return {"side": side, "entry_ref": price, "stop": float(stop), "tp": tp}


# ------------------------------- VWAP ANCHOR ---------------------------------
def vwap_anchor(ctx: Ctx, i: int, p: dict) -> dict | None:
    """VWAP Anchor v2 (portado de sentinel) — régimen VWAP multi-TF, LONG-only.

    Gate de ENTRADA (lo que decide disparar): C1 ∧ C2 ∧ O1_gate.
      C1: precio > VWAP 1h (24 barras)   C2: precio > VWAP 4h (24 barras)
      O1: frescura — skip si EMA9_1h > EMA21_1h (ya confirmó, entrada tardía)
    C3 (price > EMA50 4h) es opcional (trend_filter): en v2 sólo subía 'stars', no gateaba.
    SL = sl_atr_mult · ATR 1h. TP = tp_r · riesgo (v2: 2.0/2.5).
    """
    s = ctx.sig                                  # 1h
    if i < 30 or not np.isfinite(s.atr[i]) or s.atr[i] <= 0 or not np.isfinite(s.vwap[i]):
        return None
    price = float(s.close[i])
    if not (price > s.vwap[i]):                  # C1
        return None
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    k = aux_at(ctx, 4, T)                         # 4h cerrado ≤ T
    if k is None or not np.isfinite(ctx.aux[4].vwap[k]):
        return None
    if not (price > ctx.aux[4].vwap[k]):         # C2
        return None
    if p.get("fresh_gate", True) and s.ema9[i] > s.ema21[i]:   # O1_gate
        return None
    if p.get("trend_filter", False):             # C3 opcional
        e50 = ctx.aux[4].ema50[k]
        if not np.isfinite(e50) or not (price > e50):
            return None
    if p.get("session_filter", False):           # v2 no usa sesión (off por defecto)
        if (T // _H) % 24 not in (8, 12, 16, 20):
            return None
    atr = s.atr[i]
    stop = price - p.get("sl_atr_mult", 2.0) * atr
    risk = price - stop
    if risk <= 0:
        return None
    tp_r = p.get("tp_r", 2.5)
    tp = float(price + tp_r * risk) if tp_r > 0 else None  # None = runner (sin TP)
    return {"side": "long", "entry_ref": price, "stop": float(stop), "tp": tp}


# ------------------------------ BREAK + RETEST -------------------------------
def break_retest(ctx: Ctx, i: int, p: dict) -> dict | None:
    s = ctx.sig                                  # 4h
    if i < 30 or not np.isfinite(s.atr[i]) or s.atr[i] <= 0:
        return None
    pre_vol = s.volume[i - 28: i - 16]
    struct_h = float(np.max(s.high[i - 16: i - 8]))
    struct_l = float(np.min(s.low[i - 16: i - 8]))
    bo_close = s.close[i - 8: i]
    bo_vol = s.volume[i - 8: i]
    if pre_vol.size == 0 or bo_close.size == 0:
        return None
    price = float(s.close[i])
    atr = s.atr[i]
    base_vol = float(np.median(pre_vol))
    vol_ratio = float(np.mean(bo_vol) / base_vol) if base_vol > 0 else 99.0
    if vol_ratio >= p.get("vol_max_ratio", 1.0):        # Gate A: solo stealth (bajo vol)
        return None
    zone = p.get("retest_half_atr", 0.3) * atr
    side = level = None
    if float(np.max(bo_close)) > struct_h and abs(price - struct_h) <= zone:
        side, level = "long", struct_h
    elif float(np.min(bo_close)) < struct_l and abs(price - struct_l) <= zone:
        side, level = "short", struct_l
    if side is None:
        return None
    if p.get("long_only", False) and side == "short":
        return None
    if p.get("trend_filter", True):                      # C4: EMA50 4h alineado
        if side == "long" and not (price > s.ema50[i]):
            return None
        if side == "short" and not (price < s.ema50[i]):
            return None
    stop = level - p.get("sl_atr_mult", 1.0) * atr if side == "long" else level + p.get("sl_atr_mult", 1.0) * atr
    risk = abs(price - stop)
    if risk <= 0:
        return None
    tp_r = p.get("tp_r", 4.0)
    if tp_r <= 0:
        tp = None                                 # runner: sin TP
    else:
        tp = float(price + tp_r * risk if side == "long" else price - tp_r * risk)
    return {"side": side, "entry_ref": price, "stop": float(stop), "tp": tp}


REGISTRY = {
    "momentum_pullback": {"fn": momentum_pullback, "signal_tf_h": 2, "aux_tfs": []},
    "ema_trend_stack": {"fn": ema_trend_stack, "signal_tf_h": 4, "aux_tfs": [1]},
    "orb_breakout": {"fn": orb_breakout, "signal_tf_h": 1, "aux_tfs": [4]},
    "vwap_anchor": {"fn": vwap_anchor, "signal_tf_h": 1, "aux_tfs": [4]},
    "break_retest": {"fn": break_retest, "signal_tf_h": 4, "aux_tfs": []},
}
