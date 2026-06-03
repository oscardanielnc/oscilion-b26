"""R2 — Validación honesta POR MONEDA de estrategias portadas del proyecto BTC.

Para cada estrategia × moneda (12 monedas, 3 años, motor honesto con salidas
15m pesimistas + costos reales):
  1) DEFAULT params → train/test (ancla insesgada).
  2) BARRIDO de parámetros → se elige el mejor SOLO en train, se reporta en test
     (selección OOS honesta).
  3) WALK-FORWARD → por fold se elige config en su train y se evalúa en su test;
     se agrupan los trades OOS. Veredicto primario.

NO se promedia a ciegas (las correlacionadas con BTC ganarían peso): se reporta
por moneda y, para resumen, voto equiponderado (cada moneda cuenta 1).
Métrica primaria: expectativa por trade en R.
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import itertools
import time
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np

from config import DATA_DIR
from oscilion.backtest.engine_strat import StratParams, load_bundle, run

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
WF_BOUNDS = [int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)
             for (y, m) in [(2024, 7), (2025, 1), (2025, 7), (2026, 1)]]

GRIDS = {
    "momentum_pullback": {
        "impulse_atr_min": [0.6, 0.8, 1.0, 1.2],
        "pullback_max": [0.6, 0.8],
        "tp_r": [1.5, 2.0, 3.0, 4.0],
        "fresh_gate": [True, False],
        "long_only": [True, False],
    },
    "ema_trend_stack": {
        "atr_mult_sl": [1.0, 1.5],
        "tp_r": [2.0, 3.0, 4.0],
        "fresh_gate": [True, False],
        "session_filter": [True, False],
        "rsi_filter": [True, False],
    },
}
MIN_TRAIN = 30
MIN_TEST = 20
MIN_WF = 30


def _grid(strategy):
    g = GRIDS[strategy]
    keys = list(g)
    return [dict(zip(keys, vals)) for vals in itertools.product(*[g[k] for k in keys])]


def _stats(trades):
    if not trades:
        return {"n": 0, "exp_R": 0.0, "wr": 0.0, "pf": 0.0, "sumR": 0.0}
    R = np.array([t["R"] for t in trades])
    pnl = np.array([t["pnl"] for t in trades])
    gw = pnl[pnl > 0].sum(); gl = -pnl[pnl <= 0].sum()
    return {"n": len(trades), "exp_R": float(R.mean()), "wr": float((pnl > 0).mean()),
            "pf": float(gw / gl) if gl > 0 else float("inf"), "sumR": float(R.sum())}


def _sub(trades, lo, hi):
    return [t for t in trades if lo <= t["entry_ts"] < hi]


def _label(cfg):
    return " ".join(f"{k}={cfg[k]}" for k in sorted(cfg))


def _worker(args):
    sym, strategy = args
    bundle = load_bundle(sym, strategy)
    if bundle is None:
        return sym, None
    configs = _grid(strategy)
    # correr cada config UNA vez sobre los 3 años (causal); luego cortar por fecha
    runs = []
    for cfg in configs:
        trades = run(bundle, StratParams(strategy=strategy, params=cfg))
        runs.append((cfg, trades))
    t_max = max((t["entry_ts"] for _c, tr in runs for t in tr), default=SPLIT + 1) + 1

    # default = primer config "canónico"
    default_cfg = {"momentum_pullback": {"impulse_atr_min": 0.8, "pullback_max": 0.8,
                                         "tp_r": 2.0, "fresh_gate": True, "long_only": True},
                   "ema_trend_stack": {"atr_mult_sl": 1.0, "tp_r": 2.0, "fresh_gate": True,
                                       "session_filter": True, "rsi_filter": False}}[strategy]
    default_trades = next((tr for c, tr in runs if c == default_cfg), [])
    def_full = _stats(default_trades)
    def_train = _stats(_sub(default_trades, 0, SPLIT))
    def_test = _stats(_sub(default_trades, SPLIT, t_max))

    # barrido: elegir por train, reportar test
    best, best_train = None, -1e9
    for cfg, tr in runs:
        s = _stats(_sub(tr, 0, SPLIT))
        if s["n"] >= MIN_TRAIN and s["exp_R"] > best_train:
            best_train, best = s["exp_R"], (cfg, tr)
    sweep = None
    if best is not None:
        cfg, tr = best
        sweep = {"cfg": _label(cfg), "train": _stats(_sub(tr, 0, SPLIT)),
                 "test": _stats(_sub(tr, SPLIT, t_max))}

    # walk-forward: por fold elegir en train(<fold), evaluar en fold test
    wf_pool = []
    wf_folds = []
    bounds = WF_BOUNDS + [t_max]
    for k in range(len(bounds) - 1):
        te_lo, te_hi = bounds[k], bounds[k + 1]
        bestf, bestf_tr = None, -1e9
        for cfg, tr in runs:
            s = _stats(_sub(tr, 0, te_lo))
            if s["n"] >= MIN_TRAIN and s["exp_R"] > bestf_tr:
                bestf_tr, bestf = s["exp_R"], (cfg, tr)
        if bestf is None:
            continue
        cfg, tr = bestf
        sub = _sub(tr, te_lo, te_hi)
        wf_pool.extend(sub)
        wf_folds.append({"from": datetime.fromtimestamp(te_lo / 1000, tz=timezone.utc).strftime("%Y-%m"),
                         "cfg": _label(cfg), **_stats(sub)})
    wf = _stats(wf_pool)

    return sym, {"def_full": def_full, "def_train": def_train, "def_test": def_test,
                 "sweep": sweep, "wf": wf, "wf_folds": wf_folds}


def _verdict(r):
    """Veredicto por moneda (primario = walk-forward OOS)."""
    if r is None:
        return "—", "sin datos"
    wf = r["wf"]; dt = r["def_test"]
    if wf["n"] < MIN_WF:
        return "❔", f"WF n={wf['n']}<{MIN_WF}"
    if wf["exp_R"] >= 0.05 and dt["exp_R"] > 0:
        return "✅", "WF+default OOS positivos"
    if wf["exp_R"] > 0:
        return "🟡", "WF OOS marginal"
    return "❌", "WF OOS ≤ 0"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    L = ["# 🔬 R2 — Validación honesta por moneda (estrategias rescatadas de BTC)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas · 3 años · motor honesto "
         f"(señal 2h/4h, salida 15m pesimista) · costos taker reales · métrica = exp. por trade en R_\n",
         "_Default = params del YAML (insesgado). Sweep = mejor en TRAIN→reportado en TEST. "
         "WF = walk-forward 4 folds, config elegida por fold en su train, OOS agrupado (veredicto primario)._\n"]

    all_res = {}
    for strategy in ("ema_trend_stack", "momentum_pullback"):
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {strategy} ...", flush=True)
        with Pool(processes=min(len(SYMBOLS), 12)) as pool:
            res = dict(pool.map(_worker, [(s, strategy) for s in SYMBOLS]))
        all_res[strategy] = res
        print(f"  [{time.time()-t0:.0f}s] hecho", flush=True)

        L.append(f"## {strategy}")
        L.append("| Moneda | V | def full n/expR | def TEST n/expR | sweep TEST n/expR | **WF OOS n/expR/WR** | mejor cfg WF (último fold) |")
        L.append("|---|:--:|---|---|---|---|---|")
        survivors = []
        for sym in SYMBOLS:
            r = res.get(sym)
            v, _why = _verdict(r)
            if r is None:
                L.append(f"| {sym} | — | — | — | — | — | — |")
                continue
            df, dt = r["def_full"], r["def_test"]
            sw = r["sweep"]; wf = r["wf"]
            sw_s = f"{sw['test']['n']}/{sw['test']['exp_R']:+.3f}" if sw else "—"
            last_cfg = r["wf_folds"][-1]["cfg"] if r["wf_folds"] else "—"
            L.append(f"| {sym} | {v} | {df['n']}/{df['exp_R']:+.3f} | {dt['n']}/{dt['exp_R']:+.3f} | "
                     f"{sw_s} | **{wf['n']}/{wf['exp_R']:+.3f}/{wf['wr']*100:.0f}%** | {last_cfg} |")
            if v in ("✅", "🟡"):
                survivors.append((sym, v, wf["exp_R"], wf["n"]))

        # resumen equiponderado (cada moneda 1 voto)
        wfs = [res[s]["wf"]["exp_R"] for s in SYMBOLS if res.get(s) and res[s]["wf"]["n"] >= MIN_WF]
        npos = sum(1 for x in wfs if x > 0)
        med = float(np.median(wfs)) if wfs else 0.0
        L.append(f"\n_Resumen {strategy}: monedas con WF OOS válido={len(wfs)}, positivas={npos}, "
                 f"mediana exp_R (equiponderado)={med:+.3f}. Supervivientes (✅/🟡): "
                 f"{', '.join(s.split('/')[0]+f' ({v},{r:+.3f},n={n})' for s,v,r,n in survivors) or 'ninguna'}._\n")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "r2_strat_validation.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
