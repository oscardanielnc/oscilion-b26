"""Analysis engine: features -> scoring -> risk for the range-reversion strategy.

`analyze(sym)`            -> candidate with range, anti-sweep stop, TP (opposite
                             edge), RR, leverage and whether it is tradeable
                             (RR >= min_rr).
`rank(symbols, capital)`  -> ranking of candidates with the % of capital
                             allocated (correlation-aware allocation).

Base strategy: enter near one edge of the range, exit at the opposite one; the
stop goes beyond the liquidity cluster + ATR. If the opposite edge does not give
RR >= 2.5, that coin is NOT traded that day (a filter, not a preference).
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
    """Candidate from a DataFrame of closed candles (single source of the signal
    logic). Used by both `analyze` (live) and the backtest (on rolling windows,
    no look-ahead). No capital allocation yet.
    """
    base = {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0, "side": None}

    if df.empty or len(df) < 40:
        return {**base, "reason": "not enough data"}

    conv = conviction(df, lookback)
    side = conv["side"]
    if side is None or conv["score"] <= 0:
        return {**base, **_conv_view(conv), "reason": conv.get("reason", "no clear edge")}

    entry = conv["last"]
    lo, hi = conv["lo"], conv["hi"]
    # TP = opposite edge of the range (the natural target of the reversion)
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
    """MOMENTUM/breakout signal (the contrarian probe to reversion).

    Enters when price BREAKS a range edge (continuation), with the stop back inside
    the range (anti-fakeout + ATR) and the TP at the projected range width
    (measured move). Same output shape as `candidate_from_df`.
    """
    from oscilion.features import indicators as ind
    from oscilion.features import ranges as rng
    from oscilion.features import regime as rg

    base = {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0, "side": None}
    if df.empty or len(df) < 40:
        return {**base, "reason": "not enough data"}

    hz = rng.horizontal_range(df, lookback)
    lo, hi, mid, width = hz["lo"], hz["hi"], hz["mid"], None
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        return {**base, "reason": "range not defined"}
    width = hi - lo
    last = float(df["close"].iloc[-1])
    atr = float(ind.atr(df).iloc[-1])
    if not np.isfinite(atr) or atr <= 0:
        return {**base, "reason": "invalid ATR"}
    reg = rg.classify_regime(df, lookback)
    regime, vol_regime = reg.regime, reg.vol_regime

    if last > hi:                       # bullish breakout -> continuation long
        side, entry, stop, tp = "long", last, hi - buffer_atr * atr, last + width
        brk = (last - hi) / atr
    elif last < lo:                     # bearish breakout -> continuation short
        side, entry, stop, tp = "short", last, lo + buffer_atr * atr, last - width
        brk = (lo - last) / atr
    else:
        return {**base, "reason": "no breakout"}

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
    """Full candidate for a symbol, loading its history (live)."""
    tf = tf or config.base_timeframe
    df = store.load_bars(sym, tf)
    if df.empty or len(df) < 40:
        return {"sym": sym, "tf": tf, "tradeable": False, "score": 0.0,
                "side": None, "reason": "not enough data"}
    return candidate_from_df(sym, df, tf=tf, lookback=lookback)


def _conv_view(conv: dict) -> dict:
    return {"score": conv.get("score", 0.0), "regime": conv.get("regime"),
            "position": conv.get("position")}


def _correlations(symbols: list[str], tf: str, lookback: int = 240) -> dict:
    """Return correlation between symbols (for the allocation haircut)."""
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
    """Ranking of candidates with the % of capital allocated."""
    symbols = symbols or config.symbols
    tf = tf or config.base_timeframe

    candidates = [analyze(s, tf=tf) for s in symbols]
    tradeable = [c for c in candidates if c.get("tradeable")]
    corr = _correlations(symbols, tf)
    allocated = allocation.allocate(tradeable, capital, corr=corr)

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
            db.log_decision(c["sym"], "no-trade", c.get("reason", "no edge"))
            continue
        pid = db.log_prediction(
            c["sym"], score=c["score"], range_lo=c.get("lo"), range_hi=c.get("hi"),
            regime=c.get("regime"), stop=c.get("stop"), tp=c.get("tp"),
            rr=c.get("rr"), leverage=c.get("leverage"), components=c.get("components"),
        )
        if c["sym"] in chosen:
            db.log_decision(c["sym"], "enter",
                            f"score={c['score']} rr={c.get('rr'):.2f} w={c.get('weight'):.2%}",
                            prediction_id=pid)
        elif not c.get("tradeable"):
            db.log_decision(c["sym"], "no-trade",
                            f"rr={c.get('rr', 0):.2f} < {config.min_rr}", prediction_id=pid)
        else:
            db.log_decision(c["sym"], "wait", "not selected for the portfolio", prediction_id=pid)


def format_ranking(candidates: list[dict]) -> str:
    """Human-readable ranking table (CLI / logs)."""
    h = (f"{'SYMBOL':<16}{'SCORE':>6} {'SIDE':<6}{'REG':<7}"
         f"{'RR':>5}{'L':>6}{'STOP%':>7}{'TP%':>7}{'%CAP':>7}  RANGE")
    lines = [h, "-" * len(h)]
    for c in candidates:
        if not c.get("side"):
            lines.append(f"{c['sym']:<16}{c.get('score',0):>6.1f} {'-':<6}"
                         f"{str(c.get('regime','?'))[:6]:<7}{'-':>5}{'-':>6}"
                         f"{'-':>7}{'-':>7}{'-':>7}  {c.get('reason','')}")
            continue
        w = c.get("weight")
        rng_s = f"[{c['lo']:.4g} - {c['hi']:.4g}] pos={c['position']:.2f}"
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
    p = argparse.ArgumentParser(prog="oscilion.analysis", description="candidate ranking")
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
