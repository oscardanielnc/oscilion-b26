"""Robustez del breakout: ¿el edge es estable o concentrado? (recencia + filtros)

- Estabilidad por umbral alto (1.0 → 3.0 ATR): ¿"más fuerte = mejor" se sostiene
  y con cuántos trades sobrevive el sample?
- Desglose del umbral primario (1.5 ATR) por: TRIMESTRE (recencia / qué pasó en
  2026-H1), régimen, régimen de volatilidad y símbolo.

Métricas por-trade (sin artefacto de equity pooled). Paralelo + BLAS pin.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime, timezone
from multiprocessing import Pool

import pandas as pd

from config import DATA_DIR
from oscilion.backtest import metrics
from oscilion.backtest.engine import BTParams, backtest_symbol

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]
THRESHOLDS = [1.0, 1.5, 2.0, 2.5, 3.0]
PRIMARY = 1.5


def _worker(args):
    sym, t = args
    p = BTParams(strategy="momentum", require_confirmation=True,
                 allow_regimes=("range", "trend", "chaos"), min_breakout_atr=t)
    return backtest_symbol(sym, "1h", p)


def run_threshold(t):
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = pool.map(_worker, [(s, t) for s in SYMBOLS])
    out = []
    for tr in res:
        out.extend(tr)
    return out


def _s(trades):
    return metrics.trade_stats(trades) if trades else {"n": 0, "winrate": 0,
                                                       "profit_factor": 0, "expectancy_pct": 0}


def _row(label, s):
    return (f"| {label} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
            f"{s['expectancy_pct']*100:.3f}% |")


def _grp(df, col):
    out = []
    for k, g in df.groupby(col):
        out.append((k, _s(g.to_dict("records"))))
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    by_t = {}
    for t in THRESHOLDS:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] umbral {t} ATR ...", flush=True)
        by_t[t] = run_threshold(t)
        print(f"  [{time.time()-t0:.0f}s] {len(by_t[t])} trades", flush=True)

    L = ["# 🧱 Robustez del breakout — Oscilion",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas × 3 años · 1h · "
         f"momentum + confirm · neto de costos · por-trade_\n"]

    # estabilidad por umbral (full 3y)
    L.append("## 1) Estabilidad por umbral (3 años completos)")
    L.append("| Umbral ATR | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for t in THRESHOLDS:
        L.append(_row(f"{t}", _s(by_t[t])))

    df = pd.DataFrame(by_t[PRIMARY])
    df["q"] = df["entry_ts"].apply(
        lambda ms: (lambda d: f"{d.year}Q{(d.month-1)//3+1}")(
            datetime.fromtimestamp(ms / 1000, tz=timezone.utc)))

    L.append(f"\n## 2) Recencia — umbral {PRIMARY} ATR por TRIMESTRE")
    L.append("| Trimestre | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for q, s in sorted(_grp(df, "q")):
        L.append(_row(q, s))

    L.append(f"\n## 3) Por régimen — umbral {PRIMARY} ATR")
    L.append("| Régimen | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for k, s in _grp(df, "regime"):
        L.append(_row(str(k), s))

    L.append(f"\n## 4) Por régimen de volatilidad — umbral {PRIMARY} ATR")
    L.append("| Vol regime | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for k, s in _grp(df, "vol_regime"):
        L.append(_row(str(k), s))

    L.append(f"\n## 5) Por símbolo — umbral {PRIMARY} ATR")
    L.append("| Símbolo | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    rows = sorted(_grp(df, "sym"), key=lambda kv: kv[1]["expectancy_pct"], reverse=True)
    for k, s in rows:
        L.append(_row(k, s))
    pos = sum(1 for _k, s in rows if s["expectancy_pct"] > 0)
    L.append(f"\n_Símbolos con expectancy positiva: {pos}/{len(rows)}_")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "breakout_robustness.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
