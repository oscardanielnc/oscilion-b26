"""Test decisivo de recencia: ¿el filtro range + ruptura fuerte REPARA los
últimos trimestres negativos, o el edge está decayendo igual?

Compara: range+≥2ATR, range+≥1.5ATR y (referencia) all+≥2ATR. Para cada uno:
overall, trimestral, y split RECIENTE (2025Q4→) vs ANTERIOR (con sample agrupado,
porque al filtrar fuerte los trimestres quedan chicos). Por-trade, neto de costos.
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

CONFIGS = {
    "range + ≥2.0 ATR": dict(min_breakout_atr=2.0, allow_regimes=("range",)),
    "range + ≥1.5 ATR": dict(min_breakout_atr=1.5, allow_regimes=("range",)),
    "all + ≥2.0 ATR (ref)": dict(min_breakout_atr=2.0, allow_regimes=("range", "trend", "chaos")),
}
RECENT_CUTOFF = int(datetime(2025, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _worker(args):
    sym, kw = args
    p = BTParams(strategy="momentum", require_confirmation=True, **kw)
    return backtest_symbol(sym, "1h", p)


def run_cfg(kw):
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = pool.map(_worker, [(s, kw) for s in SYMBOLS])
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


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L = ["# 🎯 Test de recencia — filtro range + ruptura fuerte",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas × 3 años · 1h · "
         f"momentum + confirm · neto de costos · por-trade_\n"]

    for name, kw in CONFIGS.items():
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {name} ...", flush=True)
        trades = run_cfg(kw)
        print(f"  [{time.time()-t0:.0f}s] {len(trades)} trades", flush=True)
        df = pd.DataFrame(trades)

        L.append(f"## {name}")
        L.append("| Scope | N | Winrate | PF | Exp/trade |")
        L.append("|---|---:|---:|---:|---:|")
        L.append(_row("**TODO (3 años)**", _s(trades)))
        earlier = df[df["entry_ts"] < RECENT_CUTOFF].to_dict("records")
        recent = df[df["entry_ts"] >= RECENT_CUTOFF].to_dict("records")
        L.append(_row("anterior (→2025Q3)", _s(earlier)))
        L.append(_row("**RECIENTE (2025Q4→)**", _s(recent)))

        # trimestral
        df["q"] = df["entry_ts"].apply(
            lambda ms: (lambda d: f"{d.year}Q{(d.month-1)//3+1}")(
                datetime.fromtimestamp(ms / 1000, tz=timezone.utc)))
        L.append("")
        L.append("| Trimestre | N | Winrate | PF | Exp/trade |")
        L.append("|---|---:|---:|---:|---:|")
        for q, g in sorted(df.groupby("q")):
            L.append(_row(q, _s(g.to_dict("records"))))
        L.append("")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "breakout_recency.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
