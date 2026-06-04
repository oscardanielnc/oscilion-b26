"""R6 — Horizonte de los trades: ¿podemos ACORTAR sin matar el edge?

Preocupación: los EMA-trend tienen timeout de 60×4h = 240h ≈ 10 días. Multi-día =
gaps de finde + funding + "el mundo cambia". Probamos, con el motor honesto:

  baseline (hold-10d, TP fijo 4R)  vs
  time-stop DURO   (corta a N h sí o sí)                vs
  time-stop CONDIC (corta a N h SOLO si no va ≥ keep_r) vs   ← respeta #9 (no recortar ganadores)
  trailing ATR     (deja correr, stop dinámico)

Entrada FIJA (la validada); solo cambia el exit. OOS = 2025→. Métrica en R + horas
de hold + % timeout, POR MONEDA. Honestidad go/no-go: si acortar baja exp_R → no se hace.
"""
from __future__ import annotations

import os
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from datetime import datetime, timezone
from multiprocessing import Pool

import numpy as np

from config import DATA_DIR
from oscilion.backtest.engine_strat import StratParams, load_bundle, run

SPLIT = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
SYM = lambda b: f"{b}/USDT:USDT"

# foco: los EMA-trend (los de horizonte largo). ORB ya es intradía (24h).
EMA_ENTRY = {"atr_mult_sl": 1.5, "tp_r": 4.0, "fresh_gate": True,
             "session_filter": True, "rsi_filter": False}
COINS = ["BTC", "BNB", "TRX"]
MAX_HOLD = 60                       # 60×4h = 240h ≈ 10 días (baseline)

# variantes de exit a comparar (nombre -> kwargs de StratParams)
VARIANTS = {
    "baseline_10d":  dict(exit_mode="fixed_tp"),
    "tstop_120h":    dict(exit_mode="fixed_tp", time_stop_h=120),    # duro (5d)
    "tstop_96h":     dict(exit_mode="fixed_tp", time_stop_h=96),     # duro (4d)
    "tstop_72h":     dict(exit_mode="fixed_tp", time_stop_h=72),     # duro
    "tstop_48h":     dict(exit_mode="fixed_tp", time_stop_h=48),     # duro
    "tstop72_keep1": dict(exit_mode="fixed_tp", time_stop_h=72, time_stop_keep_r=1.0),  # condic.
    "tstop48_keep1": dict(exit_mode="fixed_tp", time_stop_h=48, time_stop_keep_r=1.0),  # condic.
    "trail2.0":      dict(exit_mode="trailing", trail_atr=2.0, params_tp0=True),
    "trail3.0":      dict(exit_mode="trailing", trail_atr=3.0, params_tp0=True),
}


def _stats(trades, oos=False):
    t = [x for x in trades if x["entry_ts"] >= SPLIT] if oos else trades
    if not t:
        return None
    R = np.array([x["R"] for x in t])
    hold = np.array([x["hold_h"] for x in t])
    return {"n": len(t), "exp_R": float(R.mean()), "sum_R": float(R.sum()),
            "wr": float(np.mean([x["pnl"] > 0 for x in t])),
            "hold": float(np.median(hold)), "hold_max": float(hold.max()),
            "to": float(np.mean([x["exit_reason"] == "timeout" for x in t]))}


def _worker(base):
    b = load_bundle(SYM(base), "ema_trend_stack")
    if b is None:
        return base, None
    out = {}
    for name, kw in VARIANTS.items():
        params = dict(EMA_ENTRY)
        if kw.pop("params_tp0", False):
            params["tp_r"] = 0.0                       # trailing: sin TP, corre hasta stop/time
        p = StratParams(strategy="ema_trend_stack", params=params,
                        max_hold_signal_bars=MAX_HOLD, **kw)
        out[name] = run(b, p)
    return base, out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    t0 = time.time()
    with Pool(processes=min(len(COINS), 8)) as pool:
        res = dict(pool.map(_worker, COINS))
    dt = time.time() - t0

    L = ["# 🕐 R6 — Horizonte: time-stop vs trailing vs hold-10d (EMA-trend)",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · entrada fija validada · solo cambia exit · "
         f"OOS=2025→ · {dt:.0f}s_\n",
         "Por celda: **exp_R** (full / OOS) · n · WR · **hold mediano h** · %timeout\n"]
    for base in COINS:
        r = res.get(base)
        L.append(f"## {base}")
        if r is None:
            L.append("_sin datos_\n"); continue
        L.append("| variante | exp_R full | exp_R OOS | n | WR | hold med (h) | %timeout |")
        L.append("|---|---:|---:|---:|---:|---:|---:|")
        for name in VARIANTS:
            f, o = _stats(r[name]), _stats(r[name], oos=True)
            if f is None:
                L.append(f"| {name} | — | — | 0 | — | — | — |"); continue
            oss = f"{o['exp_R']:+.3f}" if o else "—"
            L.append(f"| {name} | {f['exp_R']:+.3f} | {oss} | {f['n']} | {f['wr']:.0%} | "
                     f"{f['hold']:.0f} | {f['to']:.0%} |")
        L.append("")
    md = "\n".join(L)
    out = DATA_DIR / "reports" / "r6_exit_horizon.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
