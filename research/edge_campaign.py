"""Campaña de validación del edge (decisión go/no-go del proyecto).

Corre el backtest honesto sobre 12 monedas × 3 años (1h), comparando la lógica
naïve vs con confirmación de giro, y desglosa estabilidad temporal (semestral),
por símbolo, por régimen y sensibilidad a parámetros. Paraleliza por símbolo.

Salida: data/reports/edge_campaign.md + resumen por consola.
"""
from __future__ import annotations

import os
import sys

# permitir ejecutar como script suelto: añadir la raíz del proyecto al path
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
    "naive (sin giro)": BTParams(require_confirmation=False),
    "confirm (con giro)": BTParams(require_confirmation=True),
    "confirm + range-only": BTParams(require_confirmation=True, allow_regimes=("range",)),
    "confirm + score>=55": BTParams(require_confirmation=True, min_score=55.0),
}
CAPITAL = 10_000.0


def _worker(args):
    sym, params = args
    return sym, backtest_symbol(sym, "1h", params)


def run_config(name: str, params: BTParams) -> list[dict]:
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        results = pool.map(_worker, [(s, params) for s in SYMBOLS])
    pooled = []
    for _sym, trades in results:
        pooled.extend(trades)
    pooled.sort(key=lambda x: x["exit_ts"])
    return pooled


def _semester(ts_ms: int) -> str:
    d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return f"{d.year}-H{1 if d.month <= 6 else 2}"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L: list[str] = []
    L.append("# 🔬 Campaña de validación del edge — Oscilion")
    L.append(f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas × 3 años · "
             f"1h · capital ${CAPITAL:,.0f} · riesgo 2%/trade · RR≥2.5_\n")

    pooled_by_cfg: dict[str, list[dict]] = {}
    L.append("## 1) Comparación de configuraciones (pooled, neto de costos)")
    L.append("| Config | N | Winrate | PF | Exp/trade | Retorno | MaxDD | Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, params in CONFIGS.items():
        t0 = time.time()
        pooled = run_config(name, params)
        pooled_by_cfg[name] = pooled
        s = metrics.summarize(pooled, CAPITAL)
        L.append(f"| {name} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% | "
                 f"{s['max_drawdown']*100:.1f}% | {s['sharpe']:.2f} |")
        print(f"[{time.time()-t0:.0f}s] {name}: N={s['n']} PF={s['profit_factor']:.2f} "
              f"Sharpe={s['sharpe']:.2f} ret={s['total_return']*100:.1f}%", flush=True)

    primary = pooled_by_cfg["confirm (con giro)"]
    dfp = pd.DataFrame(primary)

    # 2) por símbolo
    L.append("\n## 2) Por símbolo (config: confirm con giro)")
    L.append("| Símbolo | N | Winrate | PF | Exp/trade | Retorno | Sharpe |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for sym, g in dfp.groupby("sym"):
        s = metrics.summarize(g.to_dict("records"), CAPITAL)
        L.append(f"| {sym} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% | {s['total_return']*100:.1f}% | {s['sharpe']:.2f} |")

    # 3) estabilidad temporal (semestral)
    L.append("\n## 3) Estabilidad temporal — semestral (confirm)")
    L.append("| Semestre | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    dfp["sem"] = dfp["exit_ts"].apply(_semester)
    for sem, g in dfp.groupby("sem"):
        s = metrics.trade_stats(g.to_dict("records"))
        L.append(f"| {sem} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% |")

    # 4) por régimen
    L.append("\n## 4) Por régimen (confirm)")
    L.append("| Régimen | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    for reg, g in dfp.groupby("regime"):
        s = metrics.trade_stats(g.to_dict("records"))
        L.append(f"| {reg} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
                 f"{s['expectancy_pct']*100:.3f}% |")

    # 5) calibración
    L.append("\n## 5) Calibración (confirm) — ¿el score se cumple?")
    L.append("| Bucket | N | Winrate | Ret medio |")
    L.append("|---|---:|---:|---:|")
    for b in metrics.calibration(primary):
        L.append(f"| {b['bucket']}-{b['bucket']+10} | {b['n']} | {b['winrate']*100:.1f}% | "
                 f"{b['avg_ret_pct']*100:.3f}% |")

    # salidas
    exits = dfp["exit_reason"].value_counts().to_dict()
    L.append(f"\n_Salidas (confirm): " + ", ".join(f"{k}={v}" for k, v in exits.items()) + "_")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "edge_campaign.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
