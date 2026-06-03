"""Motor de análisis — ensambla features → scoring → riesgo (Fase 3).

`analyze(sym)`  → candidato con rango, stop anti-barridas, TP (borde opuesto),
                  RR, apalancamiento y si es operable (RR ≥ min_rr).
`rank(symbols, capital)` → ranking de candidatos con % de capital asignado
                  (allocation con correlación) — el ENTREGABLE de la Fase 3.

Estrategia base: entrar cerca de un borde del rango, salir en el opuesto;
el stop va más allá del clúster + ATR. Si el borde opuesto no da RR ≥ 2.5,
ese día NO se opera esa moneda (filtro, no preferencia).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import config
from oscilion.data import store
from oscilion.risk import allocation, sizing, stops
from oscilion.scoring.conviction import conviction
from oscilion.persistence import db

log = logging.getLogger(__name__)


def candidate_from_df(sym: str, df: pd.DataFrame, *, tf: str, lookback: int = 96) -> dict:
    """Candidato a partir de un DataFrame de velas cerradas (fuente única de
    la lógica de señal). Lo usan tanto `analyze` (live) como el backtest
    (sobre ventanas, sin look-ahead). Sin asignación de capital aún.
    """
    base = {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0, "side": None}

    if df.empty or len(df) < 40:
        return {**base, "reason": "sin datos suficientes"}

    conv = conviction(df, lookback)
    side = conv["side"]
    if side is None or conv["score"] <= 0:
        return {**base, **_conv_view(conv), "reason": conv.get("reason", "sin borde claro")}

    entry = conv["last"]
    lo, hi = conv["lo"], conv["hi"]
    # TP = borde opuesto del rango (objetivo natural de la reversión)
    tp = hi if side == "long" else lo

    st = stops.safe_stop(df, side, entry, range_lo=lo, range_hi=hi)
    math = sizing.compute(side, entry, st.stop, tp)

    return {
        **base,
        "score": conv["score"], "side": side, "tradeable": math.tradeable,
        "regime": conv["regime"], "vol_regime": conv["vol_regime"],
        "entry": entry, "stop": st.stop, "tp": tp, "stop_basis": st.basis,
        "stop_pct": math.stop_pct, "profit_pct": math.profit_pct,
        "rr": math.rr, "leverage": math.leverage,
        "lo": lo, "hi": hi, "mid": conv["mid"], "position": conv["position"],
        "width_pct": conv["width_pct"], "atr_pct": conv["atr_pct"],
        "vol": conv["atr_pct"] if np.isfinite(conv["atr_pct"]) else 1.0,
        "components": conv["components"], "reversion": conv.get("reversion", {}),
    }


def breakout_candidate(sym: str, df: pd.DataFrame, *, tf: str, lookback: int = 96,
                       buffer_atr: float = 0.5) -> dict:
    """Señal de MOMENTUM/breakout (probe contrarian a la reversión).

    Entra cuando el precio ROMPE un borde del rango (continuación), con stop de
    vuelta dentro del rango (anti-fakeout + ATR) y TP por proyección del ancho
    del rango (measured move). Misma forma de salida que `candidate_from_df`.
    """
    from oscilion.features import indicators as ind
    from oscilion.features import ranges as rng
    from oscilion.features import regime as rg

    base = {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0, "side": None}
    if df.empty or len(df) < 40:
        return {**base, "reason": "sin datos suficientes"}

    hz = rng.horizontal_range(df, lookback)
    lo, hi, mid, width = hz["lo"], hz["hi"], hz["mid"], None
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        return {**base, "reason": "rango no definido"}
    width = hi - lo
    last = float(df["close"].iloc[-1])
    atr = float(ind.atr(df).iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        return {**base, "reason": "atr inválido"}
    reg = rg.classify_regime(df, lookback)
    regime, vol_regime = reg.regime, reg.vol_regime

    if last > hi:                       # ruptura alcista → long de continuación
        side, entry, stop, tp = "long", last, hi - buffer_atr * atr, last + width
        brk = (last - hi) / atr
    elif last < lo:                     # ruptura bajista → short de continuación
        side, entry, stop, tp = "short", last, lo + buffer_atr * atr, last - width
        brk = (lo - last) / atr
    else:
        return {**base, "reason": "sin ruptura"}

    math = sizing.compute(side, entry, stop, tp)
    score = max(0.0, min(100.0, 40 + 60 * min(1.0, brk)))
    atr_pct = atr / entry if entry else float("nan")
    return {
        **base, "score": round(score, 1), "side": side, "tradeable": math.tradeable,
        "regime": regime, "vol_regime": vol_regime, "entry": entry, "stop": stop, "tp": tp,
        "stop_pct": math.stop_pct, "profit_pct": math.profit_pct, "rr": math.rr,
        "leverage": math.leverage, "lo": lo, "hi": hi, "mid": mid,
        "position": float((last - lo) / width), "width_pct": float(width / mid),
        "atr_pct": atr_pct, "vol": atr_pct if np.isfinite(atr_pct) else 1.0,
        "components": {"breakout_atr": float(brk)},
    }


def analyze(sym: str, *, tf: str | None = None, lookback: int = 96) -> dict:
    """Candidato completo para un símbolo cargando su histórico (live)."""
    tf = tf or config.base_timeframe
    df = store.load_bars(sym, tf)
    if df.empty or len(df) < 40:
        return {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0,
                "side": None, "reason": "sin datos suficientes"}
    return candidate_from_df(sym, df, tf=tf, lookback=lookback)


def _conv_view(conv: dict) -> dict:
    return {"score": conv.get("score", 0.0), "regime": conv.get("regime"),
            "position": conv.get("position")}


def _correlations(symbols: list[str], tf: str, lookback: int = 240) -> dict:
    """Correlación de retornos entre símbolos (para el haircut de allocation)."""
    closes = {}
    for s in symbols:
        df = store.load_bars(s, tf)
        if not df.empty:
            closes[s] = df.set_index("ts")["close"].tail(lookback)
    if len(closes) < 2:
        return {}
    rets = pd.DataFrame(closes).pct_change().dropna()
    if len(rets) < 5:
        return {}
    cm = rets.corr()
    out = {}
    cols = list(cm.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            out[(a, b) if a <= b else (b, a)] = float(cm.loc[a, b])
    return out


def rank(symbols: list[str] | None = None, capital: float = 10_000.0, *,
         tf: str | None = None, persist: bool = True) -> list[dict]:
    """Ranking de candidatos con % de capital. Entregable de la Fase 3."""
    symbols = symbols or config.symbols
    tf = tf or config.base_timeframe

    candidates = [analyze(s, tf=tf) for s in symbols]
    tradeable = [c for c in candidates if c.get("tradeable")]
    corr = _correlations(symbols, tf)
    allocated = allocation.allocate(tradeable, capital, corr=corr)

    # adjuntar sizing por candidato asignado
    by_sym = {c["sym"]: c for c in allocated}
    for c in candidates:
        a = by_sym.get(c["sym"])
        if a:
            c["weight"] = a["weight"]
            c["margin"] = a["margin"]
            ps = sizing.position_size(a["margin"], c["stop_pct"])
            c["notional"] = ps["notional"]
            c["risk_amount"] = ps["risk_amount"]

    candidates.sort(key=lambda c: (c.get("weight", 0), c.get("score", 0)), reverse=True)

    if persist:
        _persist(candidates, allocated)
    return candidates


def _persist(candidates: list[dict], allocated: list[dict]) -> None:
    chosen = {c["sym"] for c in allocated}
    for c in candidates:
        if not c.get("side"):
            db.log_decision(c["sym"], "no-operar", c.get("reason", "sin borde"))
            continue
        pid = db.log_prediction(
            c["sym"], score=c["score"], range_lo=c.get("lo"), range_hi=c.get("hi"),
            regime=c.get("regime"), stop=c.get("stop"), tp=c.get("tp"),
            rr=c.get("rr"), leverage=c.get("leverage"), components=c.get("components"),
        )
        if c["sym"] in chosen:
            db.log_decision(c["sym"], "entrar",
                            f"score={c['score']} rr={c.get('rr'):.2f} w={c.get('weight'):.2%}",
                            prediction_id=pid)
        elif not c.get("tradeable"):
            db.log_decision(c["sym"], "no-operar",
                            f"rr={c.get('rr', 0):.2f} < {config.min_rr}", prediction_id=pid)
        else:
            db.log_decision(c["sym"], "esperar", "no entró en cartera", prediction_id=pid)


def format_ranking(candidates: list[dict]) -> str:
    """Tabla legible del ranking (CLI / logs)."""
    h = (f"{'SÍMBOLO':<16}{'SCORE':>6} {'SIDE':<6}{'REG':<7}"
         f"{'RR':>5}{'L':>6}{'STOP%':>7}{'TP%':>7}{'%CAP':>7}  RANGO")
    lines = [h, "-" * len(h)]
    for c in candidates:
        if not c.get("side"):
            lines.append(f"{c['sym']:<16}{c.get('score',0):>6.1f} {'—':<6}"
                         f"{str(c.get('regime','?'))[:6]:<7}{'—':>5}{'—':>6}"
                         f"{'—':>7}{'—':>7}{'—':>7}  {c.get('reason','')}")
            continue
        w = c.get("weight")
        rng_s = f"[{c['lo']:.4g} – {c['hi']:.4g}] pos={c['position']:.2f}"
        lines.append(
            f"{c['sym']:<16}{c['score']:>6.1f} {c['side']:<6}{c['regime'][:6]:<7}"
            f"{c['rr']:>5.2f}{c['leverage']:>6.2f}{c['stop_pct']*100:>6.2f}%"
            f"{c['profit_pct']*100:>6.2f}%{(w*100 if w else 0):>6.1f}%  {rng_s}"
            + ("" if c.get("tradeable") else "  (RR<min)")
        )
    return "\n".join(lines)


def main() -> None:
    import argparse

    from oscilion.logging_setup import setup_logging

    setup_logging()
    p = argparse.ArgumentParser(prog="oscilion.analysis", description="ranking de candidatos")
    p.add_argument("--capital", type=float, default=10_000.0)
    p.add_argument("--symbols", type=str, default="")
    p.add_argument("--tf", type=str, default=config.base_timeframe)
    p.add_argument("--no-persist", action="store_true")
    args = p.parse_args()

    db.init_db()
    syms = [s.strip() for s in args.symbols.split(",") if s.strip()] or config.symbols
    candidates = rank(syms, capital=args.capital, tf=args.tf, persist=not args.no_persist)
    print(format_ranking(candidates))


if __name__ == "__main__":
    main()
