"""Mapa moneda → estrategia(s) — la DIRECCIÓN confirmada de Oscilion (v1 pilot).

Decidido 2026-06-03 (ver docs/STRATEGY_MAP.md). Cada moneda recibe SOLO la(s)
estrategia(s) que se le validó(aron) en el motor honesto (full + OOS + walk-forward).
Conviccion > cantidad: si no hay edge probado, la moneda NO está aquí.

⚠️ Los `params` y `weight` son del PILOT v1 (config fija validada). Se AFINARÁN en la
fase B (mejores params por moneda, capital, multiplicadores, correlación). No hardcodear
supuestos nuevos sin validarlos con el motor honesto + forward.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Assign:
    strategy: str
    params: dict
    max_hold_signal_bars: int
    conviction: str                 # alta | media | marginal | observacion
    weight: float | None = None     # capital relativo (lo fija B; None = aún sin asignar)
    note: str = ""
    observe_only: bool = False      # True = forward-test SIN capital (alertas+stats, weight 0)


# ─────────────────────────────────────────────────────────────────────────────
# CARTERA v2 (2026-06-22) — reconstruida desde la auditoría purged-WF + barrido de
# universo (research/purged_wf.py, research/universe_scan.py). REGLA DE CAPITAL:
# un combo solo lleva capital si su exp_R es ≥ +0.10 en DOS regímenes OOS
# independientes (holdout >2025 Y 2026-YTD) con n_oos ≥ 30. Doble régimen positivo
# ⇒ no es suerte de una ventana. Config FIJA por estrategia (re-tunear por moneda
# sobreajusta en muestras chicas). Los `note` llevan: OOS-holdout / 2026-YTD.
# ─────────────────────────────────────────────────────────────────────────────

# Configs FIJAS validadas (idénticas a las que pasaron el barrido OOS).
_EMA  = dict(atr_mult_sl=1.5, tp_r=4.0, fresh_gate=True, session_filter=True, rsi_filter=False)
_ORB  = dict(range_max_pct=0.015, tp_r=4.0, fresh_gate=True, long_only=False, session_filter=True)
_VWAP = dict(sl_atr_mult=2.0, tp_r=2.5, fresh_gate=True, trend_filter=False, session_filter=False)
_BRET = dict(vol_max_ratio=1.0, retest_half_atr=0.3, tp_r=0.0, trend_filter=True, long_only=False)
_MOM  = dict(impulse_atr_min=0.8, pullback_max=0.8, tp_r=4.0, fresh_gate=True, long_only=True)


def _ema(conv, note="", max_hold=30, observe=False):
    return Assign("ema_trend_stack", dict(_EMA), max_hold,
                  "observacion" if observe else conv, note=note, observe_only=observe)


def _orb(conv, note="", observe=False):
    return Assign("orb_breakout", dict(_ORB), 24,
                  "observacion" if observe else conv, note=note, observe_only=observe)


def _vwap(conv, note="", observe=False):
    return Assign("vwap_anchor", dict(_VWAP), 120,
                  "observacion" if observe else conv, note=note, observe_only=observe)


def _bret(conv, note="", observe=False):
    return Assign("break_retest", dict(_BRET), 42,
                  "observacion" if observe else conv, note=note, observe_only=observe)


def _mom(conv, note="", observe=False):
    return Assign("momentum_pullback", dict(_MOM), 60,
                  "observacion" if observe else conv, note=note, observe_only=observe)


# NÚCLEO con capital — 12 combos, doble régimen OOS ≥ +0.10 (15m, costes reales).
PORTFOLIO: dict[str, list[Assign]] = {
    # TRX = el motor de edge (4 estrategias pasan; el veto por símbolo deja 1 viva a la vez)
    "TRX/USDT:USDT":  [_vwap("alta", "OOS+0.318 / 2026+0.851"),
                       _ema("alta",  "OOS+0.127 / 2026+0.989"),
                       _orb("alta",  "OOS+0.336 / 2026+0.445"),
                       _bret("alta", "OOS+0.190 / 2026+0.569 — promovido a capital")],
    "LINK/USDT:USDT": [_orb("alta",  "OOS+0.368 / 2026+0.387")],
    "XRP/USDT:USDT":  [_orb("media", "OOS+0.162 / 2026+0.233 — reemplaza a vwap (negativo)")],
    "DOGE/USDT:USDT": [_orb("media", "OOS+0.114 / 2026+0.400 — reemplaza a vwap (negativo)")],
    "BNB/USDT:USDT":  [_vwap("media", "OOS+0.153 / 2026+0.116"),
                       _ema("media", observe=True, note="OOS+0.358 fuerte pero 2026+0.049 flojo → observe")],
    "AVAX/USDT:USDT": [_vwap("media", "OOS+0.104 / 2026+0.154")],
    # ORO — descorrelacionado del cripto, los mejores edges del barrido (necesita backfill VM)
    "PAXG/USDT:USDT": [_bret("alta", "ORO OOS+0.469 / 2026+1.847 — mejor combo del universo"),
                       _ema("alta",  "ORO OOS+0.586 / 2026+0.230")],
    "XAU/USDT:USDT":  [_mom("media", "ORO-spot OOS+0.151 / 2026+0.250")],

    # OBSERVE (sin capital) — pasan un régimen pero fallan el otro; siguen generando
    # stats y se gradúan solas vía el gate si confirman. NO sangran capital.
    "BTC/USDT:USDT":  [_ema("media", observe=True, note="2026+0.411 fuerte / OOS+0.025 flojo → observe"),
                       _orb("media", observe=True, note="candidato; vigilar")],
    "ETH/USDT:USDT":  [_vwap("media", observe=True, note="OOS+0.111 / 2026+0.041 marginal → observe")],
    "DOT/USDT:USDT":  [_orb("media", observe=True, note="OOS+0.106 / 2026-0.069 falla reciente → observe")],
}

# PODADOS (negativos en AMBOS regímenes OOS — sin edge, retirados de la cartera):
#   BTC vwap_anchor  (OOS-0.014 / 2026-0.041)
#   DOGE vwap_anchor (OOS-0.234 / 2026-0.186)
#   XRP vwap_anchor  (OOS-0.249 / 2026-0.257)


def core_symbols() -> list[str]:
    return list(PORTFOLIO.keys())


def assignments_for(sym: str) -> list[Assign]:
    return PORTFOLIO.get(sym, [])


def all_assignments() -> list[tuple[str, Assign]]:
    return [(sym, a) for sym, lst in PORTFOLIO.items() for a in lst]
