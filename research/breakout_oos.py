"""Validación OUT-OF-SAMPLE del breakout (¿el pivot es real o data-snooping?).

El umbral de ruptura (≥X·ATR) se elige SOLO con datos de entrenamiento y se
evalúa en datos que la selección nunca vio:
  1) Split anclado: train (2023→2024) vs test (2025→2026).
  2) Walk-forward: train expansivo, test en ventanas de 6 meses; se agrupan
     todos los trades OOS (cada fold con su umbral elegido en su propio train).

Métricas por-trade (PF, winrate, expectancy) — sin el artefacto de la equity
pooled. Cada umbral se backtestea una sola vez sobre los 3 años (paralelo).
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

from config import DATA_DIR
from oscilion.backtest import metrics
from oscilion.backtest.engine import BTParams, backtest_symbol

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT"]
THRESHOLDS = [0.0, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
MIN_TRAIN = 150  # mínimo de trades en train para considerar un umbral


def _ms(y: int, m: int) -> int:
    return int(datetime(y, m, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _worker(args):
    sym, t = args
    p = BTParams(strategy="momentum", require_confirmation=True,
                 allow_regimes=("range", "trend", "chaos"), min_breakout_atr=t)
    return backtest_symbol(sym, "1h", p)


def run_threshold(t: float) -> list[dict]:
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = pool.map(_worker, [(s, t) for s in SYMBOLS])
    out = []
    for tr in res:
        out.extend(tr)
    return out


def _subset(trades, lo, hi):
    return [tr for tr in trades if lo <= tr["entry_ts"] < hi]


def _stats(trades):
    return metrics.trade_stats(trades) if trades else {"n": 0, "winrate": 0,
                                                        "profit_factor": 0, "expectancy_pct": 0}


def _select(trades_by_t, lo, hi):
    """Elige el umbral que maximiza expectancy en [lo,hi) (con n>=MIN_TRAIN)."""
    scored = {}
    for t, trs in trades_by_t.items():
        scored[t] = _stats(_subset(trs, lo, hi))
    elig = [(t, s) for t, s in scored.items() if s["n"] >= MIN_TRAIN]
    if not elig:
        elig = list(scored.items())
    return max(elig, key=lambda kv: kv[1]["expectancy_pct"])[0]


def _row(label, s):
    return (f"| {label} | {s['n']} | {s['winrate']*100:.1f}% | {s['profit_factor']:.2f} | "
            f"{s['expectancy_pct']*100:.3f}% |")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    trades_by_t: dict[float, list[dict]] = {}
    for t in THRESHOLDS:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] backtest umbral {t} ATR ...", flush=True)
        trades_by_t[t] = run_threshold(t)
        print(f"  [{time.time()-t0:.0f}s] {len(trades_by_t[t])} trades", flush=True)

    L = ["# 🔒 Validación OOS del breakout — Oscilion",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · 12 monedas × 3 años · 1h · "
         f"momentum + confirm · neto de costos · métricas por-trade_\n"]

    # rango temporal de los datos
    all_ts = [tr["entry_ts"] for trs in trades_by_t.values() for tr in trs]
    t_min, t_max = min(all_ts), max(all_ts) + 1

    # --- 1) grilla train vs test (split anclado en 2025-01) ---
    split = _ms(2025, 1)
    L.append("## 1) Grilla por umbral — train (→2024-12) vs test (2025→) ")
    L.append("| Umbral ATR | tr N | tr PF | tr exp | **te N** | **te PF** | **te exp** |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for t in THRESHOLDS:
        tr_s = _stats(_subset(trades_by_t[t], t_min, split))
        te_s = _stats(_subset(trades_by_t[t], split, t_max))
        L.append(f"| {t} | {tr_s['n']} | {tr_s['profit_factor']:.2f} | {tr_s['expectancy_pct']*100:.3f}% "
                 f"| {te_s['n']} | {te_s['profit_factor']:.2f} | {te_s['expectancy_pct']*100:.3f}% |")

    # --- 2) split anclado: elegir en train, reportar test ---
    t_star = _select(trades_by_t, t_min, split)
    train_s = _stats(_subset(trades_by_t[t_star], t_min, split))
    test_s = _stats(_subset(trades_by_t[t_star], split, t_max))
    L.append(f"\n## 2) Split anclado — umbral elegido en TRAIN = **{t_star} ATR**")
    L.append("| Periodo | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|")
    L.append(_row("TRAIN (→2024-12)", train_s))
    L.append(_row("**TEST (2025→2026, OOS)**", test_s))

    # --- 3) walk-forward (train expansivo, test 6m; pool OOS) ---
    bounds = [_ms(2024, 7), _ms(2025, 1), _ms(2025, 7), _ms(2026, 1), t_max]
    L.append("\n## 3) Walk-forward — umbral elegido por fold en su train; test OOS")
    L.append("| Fold (test) | umbral* | N | Winrate | PF | Exp/trade |")
    L.append("|---|---:|---:|---:|---:|---:|")
    oos_pool = []
    for i in range(len(bounds) - 1):
        te_lo, te_hi = bounds[i], bounds[i + 1]
        tsel = _select(trades_by_t, t_min, te_lo)          # train = todo lo previo
        sub = _subset(trades_by_t[tsel], te_lo, te_hi)
        oos_pool.extend(sub)
        s = _stats(sub)
        lbl = datetime.fromtimestamp(te_lo / 1000, tz=timezone.utc).strftime("%Y-%m")
        L.append(f"| desde {lbl} | {tsel} | {s['n']} | {s['winrate']*100:.1f}% | "
                 f"{s['profit_factor']:.2f} | {s['expectancy_pct']*100:.3f}% |")
    pool_s = _stats(oos_pool)
    L.append(_row("**POOL OOS (walk-forward)**", pool_s))

    # --- veredicto ---
    ok_anchored = test_s["profit_factor"] > 1.0 and test_s["expectancy_pct"] > 0
    ok_wf = pool_s["profit_factor"] > 1.0 and pool_s["expectancy_pct"] > 0
    if ok_anchored and ok_wf:
        verd = "✅ EDGE CONFIRMADO OOS (positivo en split anclado Y walk-forward)"
    elif ok_anchored or ok_wf:
        verd = "🟡 EDGE PARCIAL (positivo en uno de los dos OOS) — frágil"
    else:
        verd = "❌ NO confirma OOS (data-snooping probable) — el edge no sobrevive"
    L.append(f"\n## Veredicto OOS: {verd}")
    L.append(f"- Split anclado TEST: PF {test_s['profit_factor']:.2f}, exp {test_s['expectancy_pct']*100:.3f}%")
    L.append(f"- Walk-forward POOL: PF {pool_s['profit_factor']:.2f}, exp {pool_s['expectancy_pct']*100:.3f}%")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / "breakout_oos.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
