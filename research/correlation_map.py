"""Correlation map (phase B): which coins move together?

Correlation of 1h returns across the core coins (and the 12 majors for context),
full 3 years and recent (90d). Used to avoid placing the same bet several times
(e.g. BTC/BNB tend to move together -> 2 longs = 1 doubled bet).
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

import pandas as pd

from config import DATA_DIR
from oscilion.data import store

CORE = ["BTC", "BNB", "TRX", "LINK", "DOT"]
ALL = CORE + ["ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LTC"]


def _ret_matrix(bases, tail=None):
    cols = {}
    for b in bases:
        df = store.load_bars(f"{b}/USDT:USDT", "1h")
        if df.empty:
            continue
        s = df.set_index("ts")["close"]
        if tail:
            s = s.tail(tail)
        cols[b] = s
    rets = pd.DataFrame(cols).pct_change().dropna()
    return rets.corr()


def _fmt(cm, order):
    order = [c for c in order if c in cm.columns]
    head = "| | " + " | ".join(order) + " |"
    sep = "|" + "---|" * (len(order) + 1)
    rows = [head, sep]
    for r in order:
        cells = " | ".join(f"{cm.loc[r, c]:.2f}" for c in order)
        rows.append(f"| **{r}** | {cells} |")
    return "\n".join(rows)


def main():
    L = ["# Correlation map - 1h returns",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_\n",
         "## Core (full 3 years)", _fmt(_ret_matrix(CORE), CORE),
         "\n## Core (last 90 days)", _fmt(_ret_matrix(CORE, tail=24 * 90), CORE),
         "\n## The 12 majors (full 3 years)", _fmt(_ret_matrix(ALL), ALL)]
    cm = _ret_matrix(CORE)
    pairs = [(a, b, cm.loc[a, b]) for i, a in enumerate(CORE) for b in CORE[i + 1:]]
    hi = [f"{a}-{b} ({c:.2f})" for a, b, c in sorted(pairs, key=lambda x: -x[2]) if c >= 0.6]
    L.append("\n_Highly correlated core pairs (>=0.60): " + (", ".join(hi) or "none") +
             ". For phase B sizing: treat a correlated cluster as roughly one bet._")
    md = "\n".join(L)
    out = DATA_DIR / "reports" / "correlation_map.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[saved to {out}]")


if __name__ == "__main__":
    main()
