"""Simulador de CARTERA (Fase B) — una sola cuenta gestionando todas las series.

Toma los trades por serie (cada uno con su R neto y timestamps), y simula una
cuenta única con: peso de convicción por serie, límite de posiciones concurrentes
y límite por clúster de correlación (no apostar varias veces a lo mismo).

- Cada trade arriesga `risk_per_trade × weight_i` del equity vigente (respeta el
  −2%/trade: weight ≤ 1). PnL = R_neto × riesgo_arriesgado.
- Métrica de cartera: retorno, MaxDD y Sharpe REALES de la cuenta combinada.
Honesto: el R por trade ya incluye costos; aquí solo se compone la cuenta.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

_RISK = 0.02


@dataclass
class PortfolioResult:
    n_taken: int
    n_skipped: int
    total_return: float
    max_drawdown: float
    sharpe: float
    final_equity: float
    by_series: dict


def simulate(trades_by_series: dict[str, list[dict]], *, weights: dict[str, float],
             clusters: dict[str, str], capital: float = 10_000.0,
             max_concurrent: int = 3, max_per_cluster: int = 1,
             since_ts: int | None = None) -> PortfolioResult:
    """trades_by_series: {series_key: [trade...]}. weights/clusters por series_key.
    series_key se mapea a su `sym` vía el trade. `since_ts` filtra por entrada (OOS)."""
    rows = []
    for key, trades in trades_by_series.items():
        for t in trades:
            if since_ts is not None and t["entry_ts"] < since_ts:
                continue
            rows.append({"key": key, "cluster": clusters.get(key, key),
                         "entry_ts": t["entry_ts"], "exit_ts": t["exit_ts"],
                         "R": t["R"], "w": weights.get(key, 1.0)})
    if not rows:
        return PortfolioResult(0, 0, 0.0, 0.0, 0.0, capital, {})
    rows.sort(key=lambda r: r["entry_ts"])

    equity = capital
    open_pos: list[dict] = []          # {exit_ts, pnl, cluster}
    curve = []                          # (ts, equity) en cada cierre
    taken = skipped = 0
    by_series: dict[str, list[float]] = {}

    def _close_due(until_ts):
        nonlocal equity
        open_pos.sort(key=lambda o: o["exit_ts"])
        while open_pos and open_pos[0]["exit_ts"] <= until_ts:
            o = open_pos.pop(0)
            equity += o["pnl"]
            curve.append((o["exit_ts"], equity))

    for r in rows:
        _close_due(r["entry_ts"])      # realiza salidas previas a esta entrada
        clusters_open = [o["cluster"] for o in open_pos]
        if len(open_pos) >= max_concurrent or clusters_open.count(r["cluster"]) >= max_per_cluster:
            skipped += 1
            continue
        risk_amt = equity * _RISK * r["w"]
        pnl = r["R"] * risk_amt
        open_pos.append({"exit_ts": r["exit_ts"], "pnl": pnl, "cluster": r["cluster"]})
        by_series.setdefault(r["key"], []).append(r["R"])
        taken += 1
    _close_due(float("inf"))           # cierra lo que quede

    if not curve:
        return PortfolioResult(taken, skipped, 0.0, 0.0, 0.0, equity, {})
    cdf = pd.DataFrame(curve, columns=["ts", "equity"]).sort_values("ts")
    eq = cdf["equity"].to_numpy()
    peak = np.maximum.accumulate(eq)
    mdd = float(((eq - peak) / peak).min())
    s = pd.Series(eq, index=pd.to_datetime(cdf["ts"], unit="ms")).resample("1D").last().ffill()
    rets = s.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std(ddof=1) * np.sqrt(365)) if len(rets) > 2 and rets.std(ddof=1) > 0 else 0.0
    return PortfolioResult(taken, skipped, float(eq[-1] / capital - 1), mdd, sharpe, float(eq[-1]),
                           {k: {"n": len(v), "exp_R": float(np.mean(v))} for k, v in by_series.items()})
