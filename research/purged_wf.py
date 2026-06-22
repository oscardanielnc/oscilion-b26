"""Auditoría de validación — Purged Walk-Forward (2026-06-22).

Objetivo: explicar por qué el backtest del gate (+exp_R) no sobrevive en forward.
Aísla DOS fuentes de inflación sobre los combos del PORTFOLIO real:

  A) FUGA DE SELECCIÓN/IN-SAMPLE (la del gate):
     forward_results.backtest = correr los params FIJOS del portfolio sobre TODO el
     histórico y reportar exp_R. Esos params fueron elegidos por el grid de R2/R3
     porque maximizaban in-sample → reportar sobre los mismos datos. Lo medimos como
     IS (in-sample, < SPLIT) vs OOS-holdout (>= SPLIT), MISMOS params fijos, sin re-elegir.

  B) FUGA DE WALK-FORWARD SIN PURGA:
     reproducimos el WF de strat_validation (train [0,te_lo) pegado a test [te_lo,te_hi),
     eligiendo el mejor de ~N configs por fold) y lo comparamos con un WF PURGADO:
     train exige exit_ts <= te_lo - embargo (sin solापe de trades en el test) + embargo.

Salida: tabla por combo con gate(full), IS, OOS-holdout, WF-naive, WF-purged.
No toca producción. Usa datos locales (3 años). Métrica = exp_R por trade.
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

import numpy as np

from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.strategies.assignment import PORTFOLIO
from research.strat_validation import GRIDS, MAXHOLD, _grid, _sub

_H = 3_600_000

# Cortes temporales (UTC). SPLIT separa in-sample / holdout para la prueba A.
SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
# Régimen reciente: 2026-YTD (lo más cercano al periodo en vivo).
Y2026 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
# Folds de walk-forward (test windows). Expanding train antes de cada uno.
WF_BOUNDS = [int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
             for (y, m) in [(2024, 7), (2025, 1), (2025, 7), (2026, 1)]]
MIN_TRAIN = 30


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": None, "wr": None, "sumR": None}
    R = np.array([t["R"] for t in trades])
    return {"n": len(trades), "exp_R": float(R.mean()),
            "wr": float((R > 0).mean()), "sumR": float(R.sum())}


def _run_cfg(bundle, strategy, cfg, mh):
    return run(bundle, StratParams(strategy=strategy, params=cfg, max_hold_signal_bars=mh))


def _wf(runs, bounds, t_max, embargo_ms):
    """Walk-forward: por fold elige mejor cfg en train, evalúa OOS. embargo_ms=0 → naive."""
    pool = []
    for k in range(len(bounds) - 1):
        te_lo, te_hi = bounds[k], bounds[k + 1]
        best, best_tr = None, -1e9
        for cfg, tr in runs:
            # train: entradas antes del test; con purga exige cierre antes de te_lo-embargo
            if embargo_ms > 0:
                train = [t for t in tr if t["exit_ts"] <= te_lo - embargo_ms]
            else:
                train = [t for t in tr if t["entry_ts"] < te_lo]
            s = _stats(train)
            if s["n"] >= MIN_TRAIN and s["exp_R"] is not None and s["exp_R"] > best_tr:
                best_tr, best = s["exp_R"], tr
        if best is None:
            continue
        pool.extend([t for t in best if te_lo <= t["entry_ts"] < te_hi])
    return _stats(pool)


def audit_combo(sym, strategy, fixed_params, mh):
    bundle = load_bundle(sym, strategy)
    if bundle is None:
        return None
    # --- A) params FIJOS del portfolio (lo que el gate corre) ---
    fixed = _run_cfg(bundle, strategy, fixed_params, mh)
    t_max = max((t["entry_ts"] for t in fixed), default=SPLIT + 1) + 1
    gate_full = _stats(fixed)                       # = forward_results.backtest del gate
    fx_is = _stats(_sub(fixed, 0, SPLIT))           # in-sample
    fx_oos = _stats(_sub(fixed, SPLIT, t_max))      # holdout OOS, MISMOS params
    fx_2026 = _stats(_sub(fixed, Y2026, t_max))     # régimen reciente 2026-YTD
    # --- B) grid completo para WF (selección por fold) ---
    runs = [(cfg, _run_cfg(bundle, strategy, cfg, mh)) for cfg in _grid(strategy)]
    bounds_naive = WF_BOUNDS + [t_max]
    embargo = mh * _H                               # ningún trade de train solapa el test
    wf_naive = _wf(runs, bounds_naive, t_max, embargo_ms=0)
    wf_purged = _wf(runs, bounds_naive, t_max, embargo_ms=embargo)
    return {"sym": sym, "strategy": strategy, "n_cfgs": len(runs),
            "gate_full": gate_full, "fx_is": fx_is, "fx_oos": fx_oos, "fx_2026": fx_2026,
            "wf_naive": wf_naive, "wf_purged": wf_purged}


def _fmt(s):
    if not s or s["exp_R"] is None:
        return f"{s['n'] if s else 0}/—"
    return f"{s['n']}/{s['exp_R']:+.3f}"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    combos = []
    for sym, lst in PORTFOLIO.items():
        for a in lst:
            combos.append((sym, a.strategy, a.params, a.max_hold_signal_bars))
    # filtro opcional por estrategia: python -m research.purged_wf break_retest,vwap_anchor
    if len(sys.argv) > 1:
        want = set(sys.argv[1].split(","))
        combos = [c for c in combos if c[1] in want]

    print(f"Purged WF audit · {len(combos)} combos · SPLIT={datetime.utcfromtimestamp(SPLIT/1000).date()} "
          f"· folds={len(WF_BOUNDS)} · embargo=max_hold\n")
    hdr = (f"{'COMBO':<26}{'GATE full':<13}{'OOS hold':<13}{'2026-YTD':<13}"
           f"{'WF naive':<13}{'WF PURGED':<13}{'Δ leak'}")
    print(hdr); print("-" * len(hdr))
    rows = []
    for sym, strat, params, mh in combos:
        r = audit_combo(sym, strat, params, mh)
        if r is None:
            print(f"{sym.split('/')[0]+' '+strat:<26}sin bundle"); continue
        rows.append(r)
        gate = r["gate_full"]["exp_R"]
        purg = r["wf_purged"]["exp_R"]
        leak = (gate - purg) if (gate is not None and purg is not None) else None
        name = f"{sym.split('/')[0]} {strat}"
        print(f"{name:<26}{_fmt(r['gate_full']):<13}{_fmt(r['fx_oos']):<13}{_fmt(r['fx_2026']):<13}"
              f"{_fmt(r['wf_naive']):<13}{_fmt(r['wf_purged']):<13}{(f'{leak:+.3f}' if leak is not None else '—')}")

    # resumen agregado (equiponderado por combo con dato)
    def col(key):
        xs = [r[key]["exp_R"] for r in rows if r[key]["exp_R"] is not None]
        return (np.median(xs), sum(1 for x in xs if x > 0), len(xs)) if xs else (None, 0, 0)
    print("\nResumen (mediana exp_R · #positivos/#válidos):")
    for k, lab in [("gate_full", "GATE full (lo que confía)"), ("fx_oos", "OOS holdout (params fijos)"),
                   ("fx_2026", "2026-YTD (régimen reciente)"),
                   ("wf_naive", "WF naive (R2/R3)"), ("wf_purged", "WF PURGADO (honesto)")]:
        m, npos, ntot = col(k)
        print(f"  {lab:<30} {m:+.3f}   {npos}/{ntot} positivos" if m is not None else f"  {lab}: —")


if __name__ == "__main__":
    main()
