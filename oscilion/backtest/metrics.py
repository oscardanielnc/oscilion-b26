"""Backtest metrics.

On a list of closed trades (each with: ret = pnl / prior equity, pnl, mae, mfe,
rr_realized, score, regime, exit_reason, entry_ts, exit_ts):

  - trade_stats:  n, winrate, profit factor, expectancy, realized RR, MAE/MFE.
  - equity_curve: compounded equity in chronological order.
  - sharpe:       annualized on equity resampled to daily.
  - max_drawdown: worst peak-to-trough drop.
  - calibration:  real winrate per score bucket (does the score hold up?).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trade_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0}
    df = pd.DataFrame(trades)
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]
    gross_win = float(wins["pnl"].sum())
    gross_loss = float(-losses["pnl"].sum())
    n = len(df)
    return {
        "n": n,
        "winrate": float(len(wins) / n),
        "avg_win": float(wins["pnl"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["pnl"].mean()) if len(losses) else 0.0,
        "profit_factor": float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "expectancy": float(df["pnl"].mean()),
        "expectancy_pct": float(df["ret"].mean()),
        "avg_rr_realized": float(df["rr_realized"].mean()),
        "avg_mae_pct": float(df["mae"].mean()),
        "avg_mfe_pct": float(df["mfe"].mean()),
        "total_pnl": float(df["pnl"].sum()),
    }


def equity_curve(trades: list[dict], capital: float) -> pd.DataFrame:
    """Compounded equity after each trade (chronological by exit_ts)."""
    if not trades:
        return pd.DataFrame({"ts": [], "equity": []})
    df = pd.DataFrame(trades).sort_values("exit_ts")
    eq = capital * (1 + df["ret"]).cumprod()
    return pd.DataFrame({"ts": df["exit_ts"].to_numpy(), "equity": eq.to_numpy()})


def max_drawdown(equity: pd.Series | np.ndarray) -> float:
    eq = np.asarray(equity, dtype="float64")
    if eq.size == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(dd.min())


def sharpe(curve: pd.DataFrame, periods_per_year: int = 365) -> float:
    """Annualized Sharpe on daily equity returns."""
    if curve.empty or len(curve) < 3:
        return 0.0
    s = pd.Series(curve["equity"].to_numpy(),
                  index=pd.to_datetime(curve["ts"], unit="ms"))
    daily = s.resample("1D").last().ffill()
    rets = daily.pct_change().dropna()
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return 0.0
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(periods_per_year))


def calibration(trades: list[dict], bucket: int = 10) -> list[dict]:
    """Real winrate per score bucket (0-10, 10-20, ...). Measures whether the score holds up."""
    if not trades:
        return []
    df = pd.DataFrame(trades)
    df["bk"] = (df["score"] // bucket * bucket).astype(int)
    out = []
    for bk, g in df.groupby("bk"):
        out.append({"bucket": int(bk), "n": int(len(g)),
                    "winrate": float((g["pnl"] > 0).mean()),
                    "avg_ret_pct": float(g["ret"].mean())})
    return sorted(out, key=lambda r: r["bucket"])


def summarize(trades: list[dict], capital: float) -> dict:
    stats = trade_stats(trades)
    curve = equity_curve(trades, capital)
    final_eq = float(curve["equity"].iloc[-1]) if not curve.empty else capital
    stats.update({
        "total_return": float(final_eq / capital - 1),
        "final_equity": final_eq,
        "max_drawdown": max_drawdown(curve["equity"]) if not curve.empty else 0.0,
        "sharpe": sharpe(curve),
    })
    return stats
