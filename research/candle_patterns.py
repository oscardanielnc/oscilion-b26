"""R7 — Patrones de vela como FILTRO: ¿quién los respeta y qué los confirma?

Estudio de PODER DISCRIMINANTE (independiente de estrategia), 12 monedas, 3 años, 1h.

Patrones (portados de sentinel/candle_filter.py):
  Alcistas: bullish engulfing · morning star · hammer
  Bajistas: bearish engulfing · evening star · shooting star

Métrica de "respeto": tras el patrón en la barra i, con barreras simétricas ±k·ATR
y horizonte H, ¿toca primero la barrera A FAVOR del patrón? → P(dirección correcta).
Baseline ≈ 50% (un patrón sin edge). Normalizado por ATR = comparable entre monedas.

Parte 1: ranking de respeto por moneda + correlación con su volatilidad (hipótesis:
         las más volátiles respetan más).
Parte 2: qué INDICADORES presentes en la barra del patrón suben P(correcta) — confirmación.
         Sin look-ahead: todo se evalúa con datos ≤ i; la barrera mira i+1..i+H.

Honestidad: reporto n, lift y CONSISTENCIA entre monedas (un lift pooled puede ser 1-2
monedas). Patrón solo ≈ débil (lo dice sentinel); el valor está en la confluencia.
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
from oscilion.data import store
from oscilion.features import indicators as ind

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT",
           "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
           "LINK/USDT:USDT", "LTC/USDT:USDT", "DOT/USDT:USDT", "TRX/USDT:USDT",
           "SUI/USDT:USDT"]      # SUI: fuerte en Sentinel (verificar)

K_ATR = 1.0                      # barreras ±1 ATR
TF = sys.argv[1] if len(sys.argv) > 1 else "1h"
H = {"1h": 24, "15m": 96}.get(TF, 24)    # horizonte ≈ 24h real en ambos TF


# ----------------------------- detectores ------------------------------
def detect(o, h, l, c):
    """Devuelve dos máscaras booleanas (bull, bear) por barra (alcista/bajista)."""
    n = len(c)
    bull = np.zeros(n, bool); bear = np.zeros(n, bool)
    for i in range(2, n):
        # bullish engulfing
        b1 = o[i-1] - c[i-1]; b2 = c[i] - o[i]
        if b1 > 0 and b2 > 0 and o[i] <= c[i-1] and c[i] >= o[i-1] and b2 >= 1.2 * b1:
            bull[i] = True
        # morning star
        b1s = o[i-2] - c[i-2]
        if b1s > 0 and abs(c[i-1] - o[i-1]) <= 0.4 * b1s and c[i] > o[i] and c[i] >= c[i-2] + 0.3 * b1s:
            bull[i] = True
        # hammer
        body = abs(c[i] - o[i]) or 1e-9
        lo_w = min(o[i], c[i]) - l[i]; up_w = h[i] - max(o[i], c[i])
        if lo_w >= 2.0 * body and up_w <= 0.4 * body and c[i] > o[i]:
            bull[i] = True
        # bearish engulfing
        d1 = c[i-1] - o[i-1]; d2 = o[i] - c[i]
        if d1 > 0 and d2 > 0 and o[i] >= c[i-1] and c[i] <= o[i-1] and d2 >= 1.2 * d1:
            bear[i] = True
        # evening star
        d1s = c[i-2] - o[i-2]
        if d1s > 0 and abs(c[i-1] - o[i-1]) <= 0.4 * d1s and c[i] < o[i] and c[i] <= c[i-2] - 0.3 * d1s:
            bear[i] = True
        # shooting star
        if up_w >= 2.0 * body and lo_w <= 0.4 * body and c[i] < o[i]:
            bear[i] = True
    return bull, bear


def barrier_outcome(side, entry, atr_i, h, l, c, i, n, hh):
    """1 si toca primero la barrera A FAVOR del patrón en i+1..i+hh; 0 si en contra;
    si ninguna, por el signo del cierre a hh. side: +1 alcista, -1 bajista."""
    up = entry + K_ATR * atr_i
    dn = entry - K_ATR * atr_i
    end = min(i + hh, n - 1)
    for k in range(i + 1, end + 1):
        hit_up = h[k] >= up
        hit_dn = l[k] <= dn
        if hit_up and hit_dn:
            return 1 if side < 0 else 0          # pesimista: la adversa primero
        if hit_up:
            return 1 if side > 0 else 0
        if hit_dn:
            return 1 if side < 0 else 0
    fwd = c[end] - entry
    return 1 if (fwd * side) > 0 else 0


# ------------------------------- worker --------------------------------
def _worker(args):
    sym, tf, hh = args
    df = store.load_bars(sym, tf)
    if df.empty or len(df) < 300:
        return sym, None
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy(); v = df["volume"].to_numpy()
    n = len(c)
    ema9 = ind.ema(df["close"], 9).to_numpy()
    ema21 = ind.ema(df["close"], 21).to_numpy()
    ema50 = ind.ema(df["close"], 50).to_numpy()
    atr = ind.atr(df, 14).to_numpy()
    rsi = ind.rsi(df["close"], 14).to_numpy()
    vwap = ind.rolling_vwap(df, 24).to_numpy()
    atr_pct = atr / c
    med_atr_pct = float(np.nanmedian(atr_pct))
    # volumen mediano móvil (20) y atr% mediano móvil para regímenes
    medvol = np.full(n, np.nan); medatrp = np.full(n, np.nan)
    for i in range(20, n):
        medvol[i] = np.median(v[i-20:i])
        medatrp[i] = np.median(atr_pct[i-20:i])

    bull, bear = detect(o, h, l, c)

    # indicadores de confirmación a evaluar (alineados a la dirección del patrón)
    INDS = ["trend", "stack", "rsi_extremo", "vol_spike", "vwap_lado", "en_extremo", "vol_alta"]
    agg = {"n": 0, "correct": 0}
    ind_on = {k: {"n": 0, "correct": 0} for k in INDS}
    ind_off = {k: {"n": 0, "correct": 0} for k in INDS}

    for i in range(50, n - 1):
        if not (bull[i] or bear[i]):
            continue
        if not np.isfinite(atr[i]) or atr[i] <= 0 or not np.isfinite(ema50[i]):
            continue
        side = 1 if bull[i] else -1
        out = barrier_outcome(side, c[i], atr[i], h, l, c, i, n, hh)
        agg["n"] += 1; agg["correct"] += out

        # estados de confirmación (sin look-ahead)
        if side > 0:
            states = {
                "trend": c[i] > ema50[i],
                "stack": ema9[i] > ema21[i] > ema50[i],
                "rsi_extremo": np.isfinite(rsi[i]) and rsi[i] < 35,        # sobreventa (reversión alcista)
                "vol_spike": np.isfinite(medvol[i]) and v[i] > 1.5 * medvol[i],
                "vwap_lado": np.isfinite(vwap[i]) and c[i] > vwap[i],
                "en_extremo": l[i] <= np.min(l[i-20:i+1]),                 # en mínimo reciente (soporte)
                "vol_alta": np.isfinite(medatrp[i]) and atr_pct[i] > medatrp[i],
            }
        else:
            states = {
                "trend": c[i] < ema50[i],
                "stack": ema9[i] < ema21[i] < ema50[i],
                "rsi_extremo": np.isfinite(rsi[i]) and rsi[i] > 65,
                "vol_spike": np.isfinite(medvol[i]) and v[i] > 1.5 * medvol[i],
                "vwap_lado": np.isfinite(vwap[i]) and c[i] < vwap[i],
                "en_extremo": h[i] >= np.max(h[i-20:i+1]),
                "vol_alta": np.isfinite(medatrp[i]) and atr_pct[i] > medatrp[i],
            }
        for k, on in states.items():
            tgt = ind_on[k] if on else ind_off[k]
            tgt["n"] += 1; tgt["correct"] += out

    return sym, {"agg": agg, "on": ind_on, "off": ind_off,
                 "vol": med_atr_pct, "INDS": INDS}


def _rate(d):
    return (d["correct"] / d["n"]) if d["n"] else None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    t0 = time.time()
    tasks = [(s, TF, H) for s in SYMBOLS]
    with Pool(processes=min(len(SYMBOLS), 12)) as pool:
        res = dict(pool.map(_worker, tasks))
    dt = time.time() - t0

    rows = [(s, r) for s, r in res.items() if r]
    INDS = rows[0][1]["INDS"]

    # ---- Parte 1: respeto por moneda + correlación con volatilidad ----
    L = [f"# 🕯️ R7 — Patrones de vela ({TF}): ¿quién los respeta y qué los confirma?",
         f"_{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · {len(rows)} monedas · {TF} · "
         f"barreras ±{K_ATR}·ATR, H={H} barras · {dt:.0f}s_\n",
         "## Parte 1 — Respeto por moneda (P(dirección correcta); baseline≈50%)",
         "| Moneda | n patrones | **P(correcta)** | lift vs 50% | volatilidad (ATR% mediana) |",
         "|---|--:|--:|--:|--:|"]
    part1 = []
    for s, r in sorted(rows, key=lambda x: -( _rate(x[1]["agg"]) or 0)):
        pr = _rate(r["agg"]); vol = r["vol"]
        part1.append((s, pr, vol, r["agg"]["n"]))
        L.append(f"| {s.split('/')[0]} | {r['agg']['n']} | {pr*100:.1f}% | "
                 f"{(pr-0.5)*100:+.1f} pp | {vol*100:.2f}% |")
    # correlación respeto vs volatilidad (Spearman)
    prs = np.array([p for _s, p, _v, _n in part1])
    vols = np.array([v for _s, _p, v, _n in part1])
    try:
        from scipy.stats import spearmanr
        rho, pval = spearmanr(vols, prs)
    except Exception:
        rho, pval = float("nan"), float("nan")
    npos = int(np.sum(prs > 0.5))
    L.append(f"\n_Monedas con P>50% (patrón con algo de edge): {npos}/{len(prs)}. "
             f"Correlación respeto↔volatilidad (Spearman): ρ={rho:+.2f} (p={pval:.2f}). "
             f"Hipótesis 'más volátiles respetan más' → {'APOYADA' if rho>0.3 and pval<0.1 else 'NO concluyente'}._\n")

    # ---- Parte 2: confirmación por indicador (pooled equiponderado por moneda) ----
    L.append("## Parte 2 — ¿Qué indicador CONFIRMA el patrón? (lift en P(correcta))")
    L.append("Lift = P(correcta | patrón ∧ indicador) − P(correcta | patrón ∧ ¬indicador). "
             "Equiponderado por moneda; consistencia = nº monedas con lift>0.\n")
    L.append("| Indicador | P con | P sin | **lift (pp)** | consistencia | n con (tot) |")
    L.append("|---|--:|--:|--:|--:|--:|")
    ind_summary = []
    for k in INDS:
        ons, offs, cons, ntot = [], [], 0, 0
        for _s, r in rows:
            ron, roff = _rate(r["on"][k]), _rate(r["off"][k])
            if ron is not None and roff is not None and r["on"][k]["n"] >= 20:
                ons.append(ron); offs.append(roff)
                cons += 1 if (ron - roff) > 0 else 0
                ntot += r["on"][k]["n"]
        if not ons:
            L.append(f"| {k} | — | — | — | — | — |"); continue
        pc, ps = float(np.mean(ons)), float(np.mean(offs))
        ind_summary.append((k, (pc - ps) * 100, cons, len(ons)))
        L.append(f"| {k} | {pc*100:.1f}% | {ps*100:.1f}% | {(pc-ps)*100:+.1f} | "
                 f"{cons}/{len(ons)} | {ntot} |")

    ind_summary.sort(key=lambda x: -x[1])
    best = ", ".join(f"{k} ({lift:+.1f}pp, {cons}/{ncoin})" for k, lift, cons, ncoin in ind_summary[:3])
    L.append(f"\n_Top confirmadores: {best}._")

    md = "\n".join(L)
    out = DATA_DIR / "reports" / f"r7_candle_patterns_{TF}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(md)
    print(f"\n[guardado en {out}]", flush=True)


if __name__ == "__main__":
    main()
