"""Informe go/no-go del backtest (Fase 4) — la puerta de la verdad. 🚦

Agrega métricas netas (tras costos) global, por símbolo y por régimen, más la
curva de calibración (¿el score se cumple?). Emite un veredicto honesto:
si no hay edge, lo dice. Iterar con evidencia, no con manotazos (CLAUDE.md).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from oscilion.backtest import metrics

# umbrales del veredicto (conservadores; netos de costos)
GO_MIN_TRADES = 30
GO_MIN_SHARPE = 1.0
GO_MIN_PF = 1.3
GO_MIN_EXPECTANCY = 0.0   # expectancy por trade > 0


def verdict(stats: dict) -> tuple[str, list[str]]:
    """Devuelve (GO|NO-GO|INSUFICIENTE, motivos)."""
    n = stats.get("n", 0)
    if n < GO_MIN_TRADES:
        return "INSUFICIENTE", [f"solo {n} trades (< {GO_MIN_TRADES})"]
    reasons = []
    if stats["sharpe"] < GO_MIN_SHARPE:
        reasons.append(f"Sharpe {stats['sharpe']:.2f} < {GO_MIN_SHARPE}")
    if stats["profit_factor"] < GO_MIN_PF:
        reasons.append(f"PF {stats['profit_factor']:.2f} < {GO_MIN_PF}")
    if stats["expectancy_pct"] <= GO_MIN_EXPECTANCY:
        reasons.append(f"expectancy {stats['expectancy_pct']*100:.3f}% ≤ 0")
    return ("GO", ["cumple todos los umbrales"]) if not reasons else ("NO-GO", reasons)


def _row(name: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"| {name} | 0 | — | — | — | — | — | — |"
    return (f"| {name} | {s['n']} | {s['winrate']*100:.1f}% | "
            f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% | "
            f"{s.get('total_return',0)*100:.1f}% | {s.get('max_drawdown',0)*100:.1f}% | "
            f"{s.get('sharpe',0):.2f} |")


def build(result: dict) -> str:
    p = result["params"]
    pooled = result["pooled"]
    cap = p.capital
    lines: list[str] = []
    lines.append("# 🚦 Informe Go/No-Go — Backtest Oscilion")
    lines.append(f"_Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · "
                 f"TF={result['tf']} · capital=${cap:,.0f} · riesgo/trade={p.risk:.0%} · "
                 f"RR≥{p.min_rr} · regímenes={','.join(p.allow_regimes)}_\n")

    overall = metrics.summarize(pooled, cap)
    v, reasons = verdict(overall)
    badge = {"GO": "✅ GO", "NO-GO": "❌ NO-GO", "INSUFICIENTE": "⚠️ DATOS INSUFICIENTES"}[v]
    lines.append(f"## Veredicto: {badge}")
    lines.append("- " + "\n- ".join(reasons) + "\n")

    # tabla global + por símbolo
    lines.append("## Métricas netas (tras fees + funding + slippage)")
    lines.append("| Scope | N | Winrate | PF | Exp/trade | Retorno | MaxDD | Sharpe |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(_row("**GLOBAL**", overall))
    for sym, trades in result["per_symbol"].items():
        lines.append(_row(sym, metrics.summarize(trades, cap)))

    # por régimen
    lines.append("\n## Por régimen")
    lines.append("| Régimen | N | Winrate | PF | Exp/trade |")
    lines.append("|---|---:|---:|---:|---:|")
    if pooled:
        dfp = pd.DataFrame(pooled)
        for reg, g in dfp.groupby("regime"):
            s = metrics.trade_stats(g.to_dict("records"))
            lines.append(f"| {reg} | {s['n']} | {s['winrate']*100:.1f}% | "
                         f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% |")

    # salidas y MAE/MFE
    if pooled:
        dfp = pd.DataFrame(pooled)
        exits = dfp["exit_reason"].value_counts().to_dict()
        lines.append("\n## Salidas y excursiones")
        lines.append(f"- Motivos de salida: " +
                     ", ".join(f"{k}={v}" for k, v in exits.items()))
        lines.append(f"- MAE medio: {overall.get('avg_mae_pct',0)*100:.2f}% · "
                     f"MFE medio: {overall.get('avg_mfe_pct',0)*100:.2f}% · "
                     f"RR realizado medio: {overall.get('avg_rr_realized',0):.2f}")

    # calibración
    calib = metrics.calibration(pooled)
    if calib:
        lines.append("\n## Calibración (¿el score se cumple?)")
        lines.append("| Bucket score | N | Winrate real | Ret medio |")
        lines.append("|---|---:|---:|---:|")
        for b in calib:
            lines.append(f"| {b['bucket']}-{b['bucket']+10} | {b['n']} | "
                         f"{b['winrate']*100:.1f}% | {b['avg_ret_pct']*100:.3f}% |")

    return "\n".join(lines)
