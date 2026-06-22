"""Sweep de concurrencia de cartera (2026-06-22) — fija max_concurrent CON EVIDENCIA.

Simula la cuenta única (backtest/portfolio_sim) sobre los combos CON capital del
PORTFOLIO real, en la ventana OOS (>2025), barriendo max_concurrent × max_per_cluster.
Reporta retorno, MaxDD, Sharpe y trades tomados/saltados → elige el tope que más
throughput da sin disparar el drawdown.
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.backtest import portfolio_sim as PS
from oscilion.strategies import all_assignments, portfolio as P

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    caps = [(s, a) for s, a in all_assignments() if not a.observe_only]
    print(f"Sweep concurrencia · {len(caps)} combos con capital · OOS>2025\n")
    trades_by = {}
    weights, clusters = {}, {}
    for sym, a in caps:
        b = load_bundle(sym, a.strategy)
        if b is None:
            continue
        t = run(b, StratParams(strategy=a.strategy, params=a.params,
                               max_hold_signal_bars=a.max_hold_signal_bars))
        key = P.key(sym, a.strategy)
        trades_by[key] = t
        weights[key] = P.weight_of(sym, a.strategy)
        clusters[key] = P.cluster_of(sym, a.strategy)

    print(f"{'maxc':<6}{'clu':<5}{'taken':<7}{'skip':<7}{'return':<10}{'maxDD':<9}{'Sharpe'}")
    print("-" * 50)
    for mpc in (2, 3):
        for mc in (3, 4, 5, 6, 8):
            r = PS.simulate(trades_by, weights=weights, clusters=clusters,
                            max_concurrent=mc, max_per_cluster=mpc, since_ts=SPLIT)
            print(f"{mc:<6}{mpc:<5}{r.n_taken:<7}{r.n_skipped:<7}"
                  f"{r.total_return*100:>+7.1f}%  {r.max_drawdown*100:>+6.1f}%  {r.sharpe:>5.2f}")
    print("\n(return/MaxDD/Sharpe = cuenta única compuesta; R por trade ya incluye costos)")


if __name__ == "__main__":
    main()
