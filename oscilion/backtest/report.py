"""Backtest go/no-go report: the moment of truth.

Aggregates net metrics (after costs) globally, per symbol and per regime, plus
the calibration curve (does the score hold up?). Emits an honest verdict: if
there is no edge, it says so. Iterate with evidence, not with guesswork.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from oscilion.backtest import metrics

# verdict thresholds (conservative; net of costs)
GO_MIN_TRADES = 30
GO_MIN_SHARPE = 1.0
GO_MIN_PF = 1.3
GO_MIN_EXPECTANCY = 0.0   # expectancy per trade > 0


def verdict(stats: dict) -> tuple[str, list[str]]:
    """Return (GO | NO-GO | INSUFFICIENT, reasons)."""
    n = stats.get("n", 0)
    if n < GO_MIN_TRADES:
        return "INSUFFICIENT", [f"only {n} trades (< {GO_MIN_TRADES})"]
    reasons = []
    if stats["sharpe"] < GO_MIN_SHARPE:
        reasons.append(f"Sharpe {stats['sharpe']:.2f} < {GO_MIN_SHARPE}")
    if stats["profit_factor"] < GO_MIN_PF:
        reasons.append(f"PF {stats['profit_factor']:.2f} < {GO_MIN_PF}")
    if stats["expectancy_pct"] <= GO_MIN_EXPECTANCY:
        reasons.append(f"expectancy {stats['expectancy_pct']*100:.3f}% <= 0")
    return ("GO", ["meets every threshold"]) if not reasons else ("NO-GO", reasons)


def _row(name: str, s: dict) -> str:
    if s.get("n", 0) == 0:
        return f"| {name} | 0 | - | - | - | - | - | - |"
    return (f"| {name} | {s['n']} | {s['winrate']*100:.1f}% | "
            f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% | "
            f"{s.get('total_return',0)*100:.1f}% | {s.get('max_drawdown',0)*100:.1f}% | "
            f"{s.get('sharpe',0):.2f} |")


def build(result: dict) -> str:
    p = result["params"]
    pooled = result["pooled"]
    cap = p.capital
    lines: list[str] = []
    lines.append("# Go/No-Go Report - Oscilion Backtest")
    lines.append(f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | "
                 f"TF={result['tf']} | capital=${cap:,.0f} | risk/trade={p.risk:.0%} | "
                 f"RR>={p.min_rr} | regimes={','.join(p.allow_regimes)}_\n")

    overall = metrics.summarize(pooled, cap)
    v, reasons = verdict(overall)
    badge = {"GO": "GO", "NO-GO": "NO-GO", "INSUFFICIENT": "INSUFFICIENT DATA"}[v]
    lines.append(f"## Verdict: {badge}")
    lines.append("- " + "\n- ".join(reasons) + "\n")

    lines.append("## Net metrics (after fees + funding + slippage)")
    lines.append("| Scope | N | Winrate | PF | Exp/trade | Return | MaxDD | Sharpe |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(_row("**GLOBAL**", overall))
    for sym, trades in result["per_symbol"].items():
        lines.append(_row(sym, metrics.summarize(trades, cap)))

    lines.append("\n## By regime")
    lines.append("| Regime | N | Winrate | PF | Exp/trade |")
    lines.append("|---|---:|---:|---:|---:|")
    if pooled:
        dfp = pd.DataFrame(pooled)
        for reg, g in dfp.groupby("regime"):
            s = metrics.trade_stats(g.to_dict("records"))
            lines.append(f"| {reg} | {s['n']} | {s['winrate']*100:.1f}% | "
                         f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% |")

    if pooled:
        dfp = pd.DataFrame(pooled)
        exits = dfp["exit_reason"].value_counts().to_dict()
        lines.append("\n## Exits and excursions")
        lines.append("- Exit reasons: " +
                     ", ".join(f"{k}={v}" for k, v in exits.items()))
        lines.append(f"- Mean MAE: {overall.get('avg_mae_pct',0)*100:.2f}% | "
                     f"Mean MFE: {overall.get('avg_mfe_pct',0)*100:.2f}% | "
                     f"Mean realized RR: {overall.get('avg_rr_realized',0):.2f}")

    calib = metrics.calibration(pooled)
    if calib:
        lines.append("\n## Calibration (does the score hold up?)")
        lines.append("| Score bucket | N | Real winrate | Mean return |")
        lines.append("|---|---:|---:|---:|")
        for b in calib:
            lines.append(f"| {b['bucket']}-{b['bucket']+10} | {b['n']} | "
                         f"{b['winrate']*100:.1f}% | {b['avg_ret_pct']*100:.3f}% |")

    return "\n".join(lines)
