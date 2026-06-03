"""Mapa de correlaciones (Fase B) — ¿qué monedas se mueven juntas?

Correlación de retornos 1h entre las monedas del núcleo (y las 12 para contexto),
full 3 años y reciente (90d). Sirve para no apostar varias veces a lo mismo
(p.ej. BTC/BNB suelen ir juntas → 2 longs = 1 apuesta doble).
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

import numpy as np
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
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    L = ["# 🔗 Mapa de correlaciones — retornos 1h",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_\n",
         "## Núcleo (full 3 años)", _fmt(_ret_matrix(CORE), CORE),
         "\n## Núcleo (últimos 90 días)", _fmt(_ret_matrix(CORE, tail=24 * 90), CORE),
         "\n## Las 12 (full 3 años)", _fmt(_ret_matrix(ALL), ALL)]
    cm = _ret_matrix(CORE)
    pairs = [(a, b, cm.loc[a, b]) for i, a in enumerate(CORE) for b in CORE[i + 1:]]
    hi = [f"{a}-{b} ({c:.2f})" for a, b, c in sorted(pairs, key=lambda x: -x[2]) if c >= 0.6]
    L.append("\n_Pares del núcleo muy correlacionados (≥0.60): " + (", ".join(hi) or "ninguno") +
             ". Para sizing B: tratar un clúster correlacionado como ~una sola apuesta._")
    md = "\n".join(L)
    out = DATA_DIR / "reports" / "correlation_map.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]")


if __name__ == "__main__":
    main()
