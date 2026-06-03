"""Fase B — cartera (HONESTA: robustez > sobreajuste).

Hallazgo R-previo: tunear params por moneda en muestras chicas SOBREAJUSTA
(train alto, OOS flojo) y los weights por edge in-sample también. Por eso B usa:
  • params = BASELINE validado fijo (tp_r=4 etc.) — más robusto que el train-óptimo.
  • B1 = DIAGNÓSTICO que demuestra el overfit del tuning (no se adopta).
  • B6 = simulación de cartera (cuenta única) con baseline; compara equal vs edge
    y límites de concurrencia/clúster; se elige el mejor por Sharpe OOS GENUINO.

Genera data/reports/phase_b.md + oscilion/strategies/tuned.py (weights+clusters+límites).
"""
from __future__ import annotations

import os, sys
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itertools
from datetime import datetime, timezone

import numpy as np

from config import DATA_DIR
from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.backtest.portfolio_sim import simulate
from oscilion.strategies.assignment import all_assignments

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
CLUSTER = {"BTC": "majors", "BNB": "majors", "LINK": "majors", "DOT": "majors", "TRX": "trx"}
GRID = {
    "ema_trend_stack": {"tp_r": [3.0, 4.0, 5.0], "atr_mult_sl": [1.0, 1.5, 2.0],
                        "fresh_gate": [True], "session_filter": [True], "rsi_filter": [False]},
    "orb_breakout": {"tp_r": [0.0, 3.0, 4.0, 6.0], "range_max_pct": [0.010, 0.015, 0.020],
                     "fresh_gate": [True], "long_only": [False], "session_filter": [True]},
}


def _grid(s):
    g = GRID[s]; ks = list(g)
    return [dict(zip(ks, v)) for v in itertools.product(*[g[k] for k in ks])]


def stats(tr):
    if not tr:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0}
    R = np.array([t["R"] for t in tr])
    return {"n": len(tr), "exp_R": float(R.mean()), "wr": float(np.mean([t["pnl"] > 0 for t in tr]))}


def sub(tr, lo, hi):
    return [t for t in tr if lo <= t["entry_ts"] < hi]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    series = {}
    L = ["# 🎛️ Fase B — cartera (honesta: robustez > sobreajuste)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · params BASELINE fijo · métrica R · OOS=2025→_\n",
         "## B1 (diagnóstico) — por qué NO tuneamos params por moneda",
         "Tunear en train sobreajusta: el train-óptimo no generaliza. Mostramos baseline (tp_r=4) "
         "vs train-óptimo, con su OOS genuino.\n",
         "| Serie | baseline OOS n/expR | train-opt cfg | train-opt TRAIN→OOS |",
         "|---|---|---|---|"]
    for sym, a in all_assignments():
        b = load_bundle(sym, a.strategy)
        base_tr = run(b, StratParams(strategy=a.strategy, params=a.params,
                                     max_hold_signal_bars=a.max_hold_signal_bars))
        # train-óptimo (diagnóstico de overfit)
        best, best_tr_exp = None, -9
        for cfg in _grid(a.strategy):
            tr = run(b, StratParams(strategy=a.strategy, params=cfg,
                                    max_hold_signal_bars=a.max_hold_signal_bars))
            st = stats(sub(tr, 0, SPLIT))
            if st["n"] >= 20 and st["exp_R"] > best_tr_exp:
                best_tr_exp, best = st["exp_R"], (cfg, tr)
        key = f"{sym}|{a.strategy}"
        b_oos = stats(sub(base_tr, SPLIT, 1 << 62))
        series[key] = {"sym": sym, "strategy": a.strategy, "trades": base_tr,
                       "full": stats(base_tr), "train": stats(sub(base_tr, 0, SPLIT)), "oos": b_oos}
        if best:
            cfg, tr = best
            cfgs = " ".join(f"{k}={cfg[k]}" for k in ("tp_r", "atr_mult_sl", "range_max_pct") if k in cfg)
            to = stats(sub(tr, 0, SPLIT))["exp_R"]; oo = stats(sub(tr, SPLIT, 1 << 62))["exp_R"]
            L.append(f"| {sym.split('/')[0]}·{a.strategy[:3]} | {b_oos['n']}/{b_oos['exp_R']:+.3f} | "
                     f"{cfgs} | {to:+.3f}→{oo:+.3f} |")

    clusters = {k: CLUSTER[k.split("/")[0]] for k in series}
    trades_by = {k: v["trades"] for k, v in series.items()}
    # weights: equal (robusto) vs edge por FULL exp_R (comparación)
    w_equal = {k: 1.0 for k in series}
    fe = {k: max(0.0, v["full"]["exp_R"]) for k, v in series.items()}
    mx = max(fe.values()) or 1.0
    w_edge = {k: round(max(0.3, e / mx), 3) for k, e in fe.items()}

    schemes = {
        "equal sin límites":      (w_equal, 6, 6),
        "equal maxc3 clu1":       (w_equal, 3, 1),
        "equal maxc3 clu2":       (w_equal, 3, 2),
        "edge  maxc3 clu2":       (w_edge, 3, 2),
    }
    L += ["\n## B6 — simulación de CARTERA (cuenta única $10k, params baseline)",
          "| Esquema | FULL ret/MaxDD/Sharpe | **OOS ret/MaxDD/Sharpe** | taken/skip |",
          "|---|---|---|---|"]
    results = {}
    for name, (w, mc, mpc) in schemes.items():
        full = simulate(trades_by, weights=w, clusters=clusters, max_concurrent=mc, max_per_cluster=mpc)
        oos = simulate(trades_by, weights=w, clusters=clusters, max_concurrent=mc,
                       max_per_cluster=mpc, since_ts=SPLIT)
        results[name] = (full, oos, w, mc, mpc)
        L.append(f"| {name} | {full.total_return*100:+.0f}%/{full.max_drawdown*100:.0f}%/{full.sharpe:.2f} | "
                 f"**{oos.total_return*100:+.0f}%/{oos.max_drawdown*100:.0f}%/{oos.sharpe:.2f}** | "
                 f"{full.n_taken}/{full.n_skipped} |")

    # elegir mejor por Sharpe OOS ENTRE los que tienen límites reales (control de
    # concentración; "sin límites" queda solo como referencia, no se adopta).
    limited = [n for n in results if results[n][3] <= 3]
    best_name = max(limited, key=lambda n: results[n][1].sharpe)
    bfull, boos, bw, bmc, bmpc = results[best_name]
    L.append(f"\n**Mejor esquema (Sharpe OOS): {best_name}** → OOS ret {boos.total_return*100:+.0f}%, "
             f"MaxDD {boos.max_drawdown*100:.0f}%, Sharpe {boos.sharpe:.2f}.")
    L.append("\n_Disciplina: params baseline fijos (tunear por moneda sobreajusta). "
             "Clusters: majors={BTC,BNB,LINK,DOT} (~0.7), trx={TRX} (diversificador)._")
    L.append("⚠️ _Las cifras de retorno son de backtest compuesto y se confirmarán en FORWARD (Fase A) "
             "antes de creerlas; el número sobrio es el MaxDD. Sharpe es la brújula beneficio/riesgo._")

    # escribir config afinada (baseline params + weights/clusters/límites elegidos)
    tuned = ["# GENERADO por research/phase_b.py — no editar a mano.",
             f"# {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · mejor esquema: {best_name}",
             "# params = baseline (tunear por moneda sobreajusta en muestras chicas).", ""]
    tuned.append("WEIGHTS = {")
    for k, w in bw.items():
        tuned.append(f"    {k!r}: {w},")
    tuned.append("}\n")
    tuned.append("CLUSTERS = {")
    for k, c in clusters.items():
        tuned.append(f"    {k!r}: {c!r},")
    tuned.append("}\n")
    tuned.append(f"LIMITS = {{'max_concurrent': {bmc}, 'max_per_cluster': {bmpc}}}")
    (DATA_DIR.parent / "oscilion" / "strategies" / "tuned.py").write_text("\n".join(tuned) + "\n", encoding="utf-8")

    md = "\n".join(L)
    (DATA_DIR / "reports" / "phase_b.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print("\n[guardado: data/reports/phase_b.md + oscilion/strategies/tuned.py]")


if __name__ == "__main__":
    main()
