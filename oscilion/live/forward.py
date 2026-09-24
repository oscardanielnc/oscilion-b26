"""Forward validation: the concise log that answers keep/remove/fix/improve.

Runs the honest engine (single source of truth) for every coin x strategy in the
portfolio, splits trades into `backtest` (entry < inception) and `forward`
(entry >= inception, UNSEEN data) and persists a snapshot per (sym, strategy,
scope) in `forward_results`. Comparing forward vs backtest tells whether the edge
survives reality. Concise: only n, winrate, exp_R, sum_R per series.

Before deploying, `inception` is a recent holdout (pipeline self-test); on the VM
it is set to the deployment date and the forward becomes real.
"""
from __future__ import annotations

import logging

import numpy as np

from config import config
from oscilion.backtest.engine_strat import StratParams, backtest_symbol_strat
from oscilion.data import store
from oscilion.features import market_regime
from oscilion.persistence import db
from oscilion.strategies import all_assignments, portfolio as P

log = logging.getLogger(__name__)

# Below this, 0 trades does NOT mean "no edge" but "dark coin" (history never
# seeded): ~3 years is 26k 1h candles; < 1000 means no backfill.
DARK_COIN_MIN_BARS = 1000


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win_rate": None, "exp_r": None, "sum_r": None, "last_entry_ts": None}
    R = np.array([t["R"] for t in trades])
    wins = np.array([t["pnl"] > 0 for t in trades])
    return {"n": len(trades), "win_rate": float(wins.mean()),
            "exp_r": float(R.mean()), "sum_r": float(R.sum()),
            "last_entry_ts": int(max(t["entry_ts"] for t in trades))}


def refresh(inception_ms: int | None = None) -> list[dict]:
    """Recompute and persist the backtest/forward snapshot per sym x strategy."""
    inception = inception_ms or config.forward_inception_ms
    db.init_db()
    # Market regime (benchmark): loaded ONCE and reused per non-exempt combo, so
    # forward_results reflects the filter the live monitor applies.
    reg_ts, reg_bull = np.array([]), np.array([], dtype=bool)
    if config.market_regime_filter:
        reg_ts, reg_bull = market_regime.regime_series(
            store.load_bars(config.market_benchmark, config.base_timeframe),
            config.market_regime_tf_h, config.market_regime_ema)
    out: list[dict] = []
    dark: list[str] = []
    for sym, a in all_assignments():
        use_regime = config.market_regime_filter and not P.regime_exempt(sym, a.strategy)
        try:
            trades = backtest_symbol_strat(sym, StratParams(
                strategy=a.strategy, params=a.params,
                max_hold_signal_bars=a.max_hold_signal_bars,
                regime_close_ts=reg_ts if use_regime else np.array([]),
                regime_bull=reg_bull if use_regime else np.array([], dtype=bool)))
        except Exception:
            log.exception("forward refresh failed %s %s", sym, a.strategy)
            continue
        # 0 trades + tiny history = dark coin (no backfill), NOT "no edge".
        # Flagging it here keeps a silent n=0 from passing validation unnoticed.
        if not trades:
            bars = len(store.load_bars(sym, config.base_timeframe))
            if bars < DARK_COIN_MIN_BARS:
                dark.append(f"{sym.split('/')[0]}|{a.strategy}({bars} bars)")
        # Gate backtest = OOS [gate_from, inception): excludes the window where the
        # params were chosen (pre-2025) so the exp_R that decides capital is not inflated.
        gate_from = config.gate_backtest_from_ms
        if gate_from >= inception:        # inconsistent config -> do not trim
            gate_from = 0
        bt = _stats([t for t in trades if gate_from <= t["entry_ts"] < inception])
        fw = _stats([t for t in trades if t["entry_ts"] >= inception])
        # OOS sub-windows for the ROBUST gate: 2025 vs 2026-YTD (up to inception),
        # so the gate can check the recent window instead of only the average.
        split = config.gate_robust_split_ms
        oos_a = _stats([t for t in trades if gate_from <= t["entry_ts"] < min(split, inception)])
        oos_b = _stats([t for t in trades if split <= t["entry_ts"] < inception])
        for scope, s in (("backtest", bt), ("forward", fw), ("oos_a", oos_a), ("oos_b", oos_b)):
            db.upsert_forward_result(sym, a.strategy, scope, **s)
        out.append({"sym": sym, "strategy": a.strategy, "backtest": bt, "forward": fw})
    if dark:
        log.warning("forward: %d dark series without history: %s", len(dark), ", ".join(dark))
        db.log_event("WARN", "live.forward",
                     f"{len(dark)} series without history (backfill pending): {', '.join(dark)}")
    db.log_event("INFO", "live.forward", f"forward refresh: {len(out)} series, {len(dark)} dark")
    return out


def curve() -> list[dict]:
    """Read the persisted snapshot (for the API/dashboard)."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT sym, strategy, scope, n, win_rate, exp_r, sum_r, last_entry_ts, updated_at"
            " FROM forward_results ORDER BY sym, strategy, scope"
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    """CLI: show backtest vs forward per coin x strategy.

    By default it READS the persisted table (filled by the service with the real
    deployment inception, so it matches the dashboard). --recompute recomputes on
    the fly (uses the config inception; useful offline)."""
    import sys
    from oscilion.logging_setup import setup_logging

    setup_logging()

    recompute = "--recompute" in sys.argv
    if recompute:
        refresh()
    rows = curve()
    if not rows:                                  # no service snapshot yet
        refresh()
        rows = curve()

    by: dict[tuple, dict] = {}
    for r in rows:
        by.setdefault((r["sym"], r["strategy"]), {})[r["scope"]] = r

    print(f"\n{'COIN':<7}{'STRATEGY':<18}{'BACKTEST (n/expR)':<22}{'FORWARD (n/expR)':<22}VERDICT")
    print("-" * 80)
    for (sym, strat), d in sorted(by.items()):
        bt, fw = d.get("backtest", {}), d.get("forward", {})
        be = f"{bt.get('n',0)}/{bt['exp_r']:+.3f}" if bt.get("exp_r") is not None else f"{bt.get('n',0)}/-"
        fe = f"{fw.get('n',0)}/{fw['exp_r']:+.3f}" if fw.get("exp_r") is not None else f"{fw.get('n',0)}/-"
        if fw.get("exp_r") is None or fw.get("n", 0) < 10:
            v = "accumulating forward"
        elif fw["exp_r"] > 0:
            v = "holds"
        else:
            v = "review"
        print(f"{sym.split('/')[0]:<7}{strat:<18}{be:<22}{fe:<22}{v}")


if __name__ == "__main__":
    main()
