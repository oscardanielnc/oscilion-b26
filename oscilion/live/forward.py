"""Validación forward (Fase A) — el LOG conciso que responde keep/remove/fix/improve.

Corre el motor honesto (única fuente de verdad) para cada moneda×estrategia del
portfolio, separa los trades en `backtest` (entrada < inception) y `forward`
(entrada ≥ inception, datos NO vistos) y persiste un snapshot por (sym, strategy,
scope) en `forward_results`. Comparar forward vs backtest dice si el edge sobrevive
en la realidad. Conciso: solo n, winrate, exp_R, sum_R por serie.

Pre-deploy el `inception` es un holdout reciente (auto-test del pipeline); al
desplegar en la VM se fija a la fecha de despliegue y el forward se vuelve real.
"""
from __future__ import annotations

import logging

import numpy as np

from config import config
from oscilion.backtest.engine_strat import StratParams, backtest_symbol_strat
from oscilion.persistence import db
from oscilion.strategies import all_assignments

log = logging.getLogger(__name__)


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win_rate": None, "exp_r": None, "sum_r": None, "last_entry_ts": None}
    R = np.array([t["R"] for t in trades])
    wins = np.array([t["pnl"] > 0 for t in trades])
    return {"n": len(trades), "win_rate": float(wins.mean()),
            "exp_r": float(R.mean()), "sum_r": float(R.sum()),
            "last_entry_ts": int(max(t["entry_ts"] for t in trades))}


def refresh(inception_ms: int | None = None) -> list[dict]:
    """Recalcula y persiste el snapshot backtest/forward por sym×strategy."""
    inception = inception_ms or config.forward_inception_ms
    db.init_db()
    out: list[dict] = []
    for sym, a in all_assignments():
        try:
            trades = backtest_symbol_strat(sym, StratParams(
                strategy=a.strategy, params=a.params,
                max_hold_signal_bars=a.max_hold_signal_bars))
        except Exception:
            log.exception("forward refresh falló %s %s", sym, a.strategy)
            continue
        bt = _stats([t for t in trades if t["entry_ts"] < inception])
        fw = _stats([t for t in trades if t["entry_ts"] >= inception])
        for scope, s in (("backtest", bt), ("forward", fw)):
            db.upsert_forward_result(sym, a.strategy, scope, **s)
        out.append({"sym": sym, "strategy": a.strategy, "backtest": bt, "forward": fw})
    db.log_event("INFO", "live.forward", f"forward refresh: {len(out)} series")
    return out


def curve() -> list[dict]:
    """Lee el snapshot persistido (para API/frontend)."""
    with db._lock:
        rows = db.get_connection().execute(
            "SELECT sym, strategy, scope, n, win_rate, exp_r, sum_r, last_entry_ts, updated_at"
            " FROM forward_results ORDER BY sym, strategy, scope"
        ).fetchall()
    return [dict(r) for r in rows]


def main() -> None:
    """CLI: recalcula y muestra backtest vs forward por moneda×estrategia."""
    import sys
    from oscilion.logging_setup import setup_logging

    setup_logging()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    res = refresh()
    print(f"\n{'MONEDA':<7}{'ESTRATEGIA':<18}{'BACKTEST (n/expR)':<22}{'FORWARD (n/expR)':<22}VEREDICTO")
    print("-" * 80)
    for r in res:
        bt, fw = r["backtest"], r["forward"]
        be = f"{bt['n']}/{bt['exp_r']:+.3f}" if bt["exp_r"] is not None else f"{bt['n']}/—"
        fe = f"{fw['n']}/{fw['exp_r']:+.3f}" if fw["exp_r"] is not None else f"{fw['n']}/—"
        if fw["exp_r"] is None or fw["n"] < 10:
            v = "⏳ poca muestra forward"
        elif fw["exp_r"] > 0:
            v = "✅ aguanta"
        else:
            v = "⚠️ revisar"
        print(f"{r['sym'].split('/')[0]:<7}{r['strategy']:<18}{be:<22}{fe:<22}{v}")


if __name__ == "__main__":
    main()
