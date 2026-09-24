"""Curated live signals for the dashboard: only what adds value.

For each coin x strategy it returns: price, direction according to ITS strategy,
proposed SL/TP, RR, relevant levels (EMAs for trend; range for breakout), RSI
only if the strategy uses it, and a checklist of conditions (why it fires or what
is missing). State: IN TRADE / SIGNAL ACTIVE / WAITING.

No filler indicators. Reads from the store (refreshed by the monitor every tick).
"""
from __future__ import annotations

import numpy as np

from oscilion.data import store
from oscilion.persistence import db
from oscilion.strategies import all_assignments, library as S
from oscilion.strategies.context import build_ctx

_H = 3_600_000


def _price_now(sym: str) -> float | None:
    m15 = store.load_bars(sym, "15m")
    return float(m15["close"].iloc[-1]) if not m15.empty else None


def _ema_view(ctx, i, a, price, atr) -> dict:
    s = ctx.sig
    e9, e21, e50, rsi = float(s.ema9[i]), float(s.ema21[i]), float(s.ema50[i]), float(s.rsi[i])
    margin = a.params.get("pullback_margin", 0.0015)
    recent_low = float(np.min(s.low[i - a.params.get("pullback_lookback", 3) + 1: i + 1]))
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    fresh_ok = True
    k = S.aux_at(ctx, 1, T)
    if k is not None:
        fresh_ok = not (ctx.aux[1].ema9[k] > ctx.aux[1].ema21[k])
    session_ok = (T // _H) % 24 in (8, 12, 16, 20)
    stop = price - a.params.get("atr_mult_sl", 1.5) * atr
    risk = price - stop
    tp = price + a.params.get("tp_r", 4.0) * risk
    checklist = [
        {"label": "Stack 9>21>50 (4H)", "ok": bool(e9 > e21 > e50)},
        {"label": "Price > EMA50", "ok": bool(price > e50)},
        {"label": "Pullback to EMA21", "ok": bool(recent_low <= e21 * (1 + margin) and price > e21)},
        {"label": "1H not yet bullish (freshness)", "ok": bool(fresh_ok)},
        {"label": "EU/NY session", "ok": bool(session_ok)},
    ]
    return {
        "direction": "long", "bias": "long",
        "entry": round(price, 6), "stop": round(stop, 6), "tp": round(tp, 6),
        "stop_pct": round(risk / price * 100, 2) if price else None,
        "tp_pct": round((tp - price) / price * 100, 2) if price else None,
        "rr": a.params.get("tp_r", 4.0),
        "levels": {"EMA9": round(e9, 6), "EMA21": round(e21, 6), "EMA50": round(e50, 6)},
        "indicators": {"RSI": round(rsi, 1), "RSI_healthy": bool(40 <= rsi <= 65)},
        "checklist": checklist,
    }


def _orb_view(ctx, i, a, price, atr) -> dict:
    s = ctx.sig                                   # 1h
    rng = a.params.get("range_bars", 6)
    hi = float(np.max(s.high[i - rng: i])); lo = float(np.min(s.low[i - rng: i]))
    mid = (hi + lo) / 2
    width_pct = (hi - lo) / mid * 100 if mid else None
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    k = S.aux_at(ctx, 4, T)
    ema50_4h = float(ctx.aux[4].ema50[k]) if k is not None else None
    session_ok = 8 <= (T // _H) % 24 < 21
    narrow_ok = width_pct is not None and width_pct <= a.params.get("range_max_pct", 0.015) * 100
    if price > hi:
        direction = bias = "long"            # real breakout up
    elif price < lo:
        direction = bias = "short"           # real breakout down
    else:
        # Inside the range: NO breakout -> no committed direction.
        # `bias` is only the nearest edge (a visual hint), not a signal.
        direction = "neutral"
        bias = "long" if (hi - price) <= (price - lo) else "short"
    if bias == "long":
        stop = min(lo - a.params.get("sl_atr_buf", 0.5) * atr, price - atr)
        risk = price - stop
        tp = price + a.params.get("tp_r", 4.0) * risk
        ema_ok = ema50_4h is not None and price > ema50_4h
    else:
        stop = max(hi + a.params.get("sl_atr_buf", 0.5) * atr, price + atr)
        risk = stop - price
        tp = price - a.params.get("tp_r", 4.0) * risk
        ema_ok = ema50_4h is not None and price < ema50_4h
    checklist = [
        {"label": f"Breaks {rng}h range", "ok": bool(price > hi or price < lo)},
        {"label": "Narrow range (<1.5%)", "ok": bool(narrow_ok)},
        {"label": "4H EMA50 aligned", "ok": bool(ema_ok)},
        {"label": "EU/NY session", "ok": bool(session_ok)},
    ]
    return {
        "direction": direction, "bias": bias,
        "entry": round(price, 6), "stop": round(stop, 6), "tp": round(tp, 6),
        "stop_pct": round(abs(price - stop) / price * 100, 2) if price else None,
        "tp_pct": round(abs(tp - price) / price * 100, 2) if price else None,
        "rr": a.params.get("tp_r", 4.0),
        "levels": {"Range_hi": round(hi, 6), "Range_lo": round(lo, 6),
                   "EMA50_4H": round(ema50_4h, 6) if ema50_4h else None,
                   "width_%": round(width_pct, 2) if width_pct else None},
        "indicators": {},                          # ORB does not use RSI: not shown
        "checklist": checklist,
    }


def _vwap_view(ctx, i, a, price, atr) -> dict:
    """vwap_anchor view: 1h/4h VWAP, freshness, SL/TP and the real checklist (C1/C2/O1)."""
    s = ctx.sig
    vwap1 = float(s.vwap[i]) if np.isfinite(s.vwap[i]) else None
    T = int(s.ts[i]) + ctx.sig_tf_h * _H
    k = S.aux_at(ctx, 4, T)
    vwap4 = float(ctx.aux[4].vwap[k]) if (k is not None and np.isfinite(ctx.aux[4].vwap[k])) else None
    ema50_4h = float(ctx.aux[4].ema50[k]) if (k is not None and np.isfinite(ctx.aux[4].ema50[k])) else None
    fresh_ok = not (s.ema9[i] > s.ema21[i])
    c1 = vwap1 is not None and price > vwap1
    c2 = vwap4 is not None and price > vwap4
    direction = "long" if (c1 and c2 and fresh_ok) else "neutral"
    stop = price - a.params.get("sl_atr_mult", 2.0) * atr
    risk = price - stop
    tp_r = a.params.get("tp_r", 2.5)
    tp = price + tp_r * risk if tp_r else price
    checklist = [
        {"label": "Price > 1h VWAP", "ok": bool(c1)},
        {"label": "Price > 4h VWAP", "ok": bool(c2)},
        {"label": "Freshness (1h EMA9<EMA21)", "ok": bool(fresh_ok)},
    ]
    return {
        "direction": direction, "bias": "long",
        "entry": round(price, 6), "stop": round(stop, 6),
        "tp": round(tp, 6) if tp_r else "no TP",
        "stop_pct": round(risk / price * 100, 2) if price else None,
        "tp_pct": round((tp - price) / price * 100, 2) if (price and tp_r) else None,
        "rr": tp_r if tp_r else "no TP",
        "levels": {"VWAP_1h": round(vwap1, 6) if vwap1 else None,
                   "VWAP_4h": round(vwap4, 6) if vwap4 else None,
                   "EMA50_4h": round(ema50_4h, 6) if ema50_4h else None},
        "indicators": {},
        "checklist": checklist,
    }


def _generic_view(a, price, cand) -> dict:
    """Honest view for strategies without a dedicated one (e.g. break_retest):
    reflects the REAL candidate if there is one, without inventing levels."""
    rr = a.params.get("tp_r", 0.0)
    if cand:
        side = cand["side"]
        stop = float(cand["stop"])
        tp = float(cand["tp"]) if cand.get("tp") is not None else None   # None = runner
        risk = abs(price - stop)
        return {
            "direction": side, "bias": side,
            "entry": round(price, 6), "stop": round(stop, 6),
            "tp": round(tp, 6) if tp is not None else "runner",
            "stop_pct": round(risk / price * 100, 2) if price else None,
            "tp_pct": round(abs(tp - price) / price * 100, 2) if (price and rr and tp is not None) else None,
            "rr": rr if rr else "no TP",
            "levels": {}, "indicators": {},
            "checklist": [{"label": "Stealth breakout + retest confirmed", "ok": True}],
        }
    return {
        "direction": "neutral", "bias": "long",
        "entry": round(price, 6), "stop": round(price, 6), "tp": round(price, 6),
        "stop_pct": None, "tp_pct": None, "rr": rr if rr else "no TP",
        "levels": {}, "indicators": {},
        "checklist": [{"label": "Waiting for stealth breakout + retest", "ok": False}],
    }


def live_signals() -> list[dict]:
    out: list[dict] = []
    states = db.load_monitor_states()
    for sym, a in all_assignments():
        ctx = build_ctx(sym, a.strategy, tail_1h=1500)
        if ctx is None:
            continue
        i = len(ctx.sig.ts) - 1
        if i < 55:
            continue
        atr = float(ctx.sig.atr[i]) if np.isfinite(ctx.sig.atr[i]) else 0.0
        price = _price_now(sym) or float(ctx.sig.close[i])
        cand = S.REGISTRY[a.strategy]["fn"](ctx, i, a.params)
        if a.strategy == "ema_trend_stack":
            view = _ema_view(ctx, i, a, price, atr)
        elif a.strategy == "orb_breakout":
            view = _orb_view(ctx, i, a, price, atr)
        elif a.strategy == "vwap_anchor":
            view = _vwap_view(ctx, i, a, price, atr)
        else:
            view = _generic_view(a, price, cand)        # break_retest and others
        st = states.get(f"{sym}|{a.strategy}", {})
        pos = st.get("position")
        n_ok = sum(1 for c in view["checklist"] if c["ok"])
        state = "IN TRADE" if pos else ("SIGNAL ACTIVE" if cand else "WAITING")
        # max trade horizon (timeout) = max_hold x signal TF
        horizon_h = a.max_hold_signal_bars * ctx.sig_tf_h
        if horizon_h >= 48:
            horizon = f"swing, up to ~{horizon_h // 24} days"
        else:
            horizon = f"short, up to ~{horizon_h} h"
        out.append({
            "sym": sym, "base": sym.split("/")[0], "strategy": a.strategy,
            "conviction": a.conviction, "observe_only": a.observe_only,
            "signal_tf": f"{ctx.sig_tf_h}h",
            "price": round(price, 6), "state": state, "signal_active": cand is not None,
            "in_trade": pos is not None, "position": pos,
            "horizon": horizon, "horizon_h": horizon_h,
            "checklist_ok": n_ok, "checklist_total": len(view["checklist"]),
            **view,
        })
    return out
