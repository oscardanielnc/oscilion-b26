"""Motor honesto para estrategias direccionales (Fase de pruebas R1).

- Señal en TF coarse (2h/4h) resampleado del 1h; SIN look-ahead.
- Salida resuelta en TF FINO (15m por defecto) con desempate PESIMISTA
  (stop antes que TP dentro de la misma vela fina).
- Entrada al open de la primera vela fina tras el cierre de la señal (T).
- Costos reales (fees taker/maker, slippage, funding 8h).
- Métrica primaria por trade en **R** (pnl / presupuesto de riesgo), robusta a
  la compauesta de equity. Distinción POR MONEDA (no se promedia a ciegas).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from config import config
from oscilion.backtest.costs import DEFAULT_COSTS, CostModel
from oscilion.data import store
from oscilion.strategies import library as S
from oscilion.strategies.context import build_ctx

log = logging.getLogger(__name__)
_H = 3_600_000


@dataclass
class StratParams:
    strategy: str = "momentum_pullback"
    risk: float = 0.02
    exit_tf: str = "15m"
    max_hold_signal_bars: int = 60        # timeout en barras de la señal
    costs: CostModel = field(default_factory=lambda: DEFAULT_COSTS)
    maker_entry: bool = False             # R4 lo activará
    exit_mode: str = "fixed_tp"           # fixed_tp | trailing (R5)
    trail_atr: float = 2.0                # distancia de trailing en ATR de la señal
    be_at_r: float = 1.0                  # mover a break-even a +be_at_r·R
    # time-stop (R6): tras `time_stop_h` horas, salir a mercado SALVO que el trade
    # vaya ganando ≥ `time_stop_keep_r`·R (deja correr ganadores — aprendizaje #9).
    # 0 = desactivado. keep_r enorme = time-stop duro (corta sí o sí).
    time_stop_h: float = 0.0
    time_stop_keep_r: float = 1e9
    params: dict = field(default_factory=dict)


@dataclass
class CoinBundle:
    """Datos precargados de una moneda+estrategia (caro de construir, reusable
    en barridos de parámetros)."""
    sym: str
    ctx: S.Ctx
    ets: np.ndarray
    eo: np.ndarray
    eh: np.ndarray
    el: np.ndarray
    ec: np.ndarray
    fund_ts: np.ndarray
    fund_rate: np.ndarray


def load_bundle(sym: str, strategy: str, exit_tf: str = "15m") -> CoinBundle | None:
    ctx = build_ctx(sym, strategy)
    if ctx is None:
        return None
    exit_df = store.load_bars(sym, exit_tf)
    if exit_df.empty:
        return None
    funding = store.load_funding(sym)
    return CoinBundle(
        sym=sym, ctx=ctx,
        ets=exit_df["ts"].to_numpy(),
        eo=exit_df["open"].to_numpy(), eh=exit_df["high"].to_numpy(),
        el=exit_df["low"].to_numpy(), ec=exit_df["close"].to_numpy(),
        fund_ts=funding["ts"].to_numpy() if not funding.empty else np.array([]),
        fund_rate=funding["funding_rate"].to_numpy() if not funding.empty else np.array([]),
    )


def run(bundle: CoinBundle, p: StratParams) -> list[dict]:
    spec = S.REGISTRY[p.strategy]
    fn = spec["fn"]
    ctx = bundle.ctx
    sym = bundle.sym
    ets, eo, eh, el, ec = bundle.ets, bundle.eo, bundle.eh, bundle.el, bundle.ec
    fund_ts, fund_rate = bundle.fund_ts, bundle.fund_rate
    n_exit = len(ets)
    sig_tf_ms = ctx.sig_tf_h * _H
    max_hold_ms = p.max_hold_signal_bars * sig_tf_ms

    equity = 10_000.0
    trades: list[dict] = []
    busy_until_ts = -1                       # no reevaluar señal mientras hay posición
    sig = ctx.sig
    for i in range(len(sig.ts)):
        T = int(sig.ts[i]) + sig_tf_ms       # cierre de la señal
        if T <= busy_until_ts:
            continue
        cand = fn(ctx, i, p.params)
        if cand is None:
            continue

        # entrada: primera vela fina con open_ts >= T
        ei = int(np.searchsorted(ets, T, side="left"))
        if ei >= n_exit:
            break
        side = cand["side"]
        maker = p.maker_entry
        entry_px = p.costs.fill_price(eo[ei], side, is_entry=True, maker=maker)
        stop, tp = cand["stop"], cand["tp"]            # tp=None = runner (sin TP)
        tp_lvl = S.tp_barrier(tp, side)                # ±inf si runner: nunca dispara
        # re-validar geometría con el fill real
        risk_dist = (entry_px - stop) if side == "long" else (stop - entry_px)
        if risk_dist <= 0:
            continue
        # piso de stop (= monitor): riesgo fijo / stop→0 dispara el notional
        if risk_dist / entry_px < config.min_stop_pct:
            continue
        risk_amt = equity * p.risk
        notional = risk_amt / (risk_dist / entry_px)
        entry_fee = p.costs.fee(notional, maker=maker)
        atr_sig = float(sig.atr[i]) if np.isfinite(sig.atr[i]) else risk_dist

        # caminar velas finas hasta salida (pesimista: stop antes que TP) / timeout
        exit_px = exit_reason = None
        k = ei
        deadline = T + max_hold_ms
        ts_on = p.time_stop_h > 0
        ts_ms = p.time_stop_h * _H

        def _time_stop(kk: int):
            """Si toca el time-stop y el trade NO va ganando ≥ keep_r → salir al cierre."""
            if not ts_on or (ets[kk] - T) < ts_ms:
                return None
            ur = ((ec[kk] - entry_px) if side == "long" else (entry_px - ec[kk])) / risk_dist
            return None if ur >= p.time_stop_keep_r else (float(ec[kk]), "time")

        if p.exit_mode == "trailing":
            trail_d = p.trail_atr * atr_sig
            be_move = p.be_at_r * risk_dist
            cur_stop = stop
            best = entry_px
            while k < n_exit and ets[k] <= deadline:
                hi, lo = eh[k], el[k]
                # 1) chequear stop con el nivel vigente (de barras previas) — pesimista
                if (side == "long" and lo <= cur_stop) or (side == "short" and hi >= cur_stop):
                    exit_px, exit_reason = cur_stop, "trail"; break
                ts = _time_stop(k)
                if ts:
                    exit_px, exit_reason = ts; break
                # 2) actualizar mejor precio y ratchet del stop
                if side == "long":
                    best = max(best, hi)
                    if best - entry_px >= be_move:
                        cur_stop = max(cur_stop, entry_px)
                    cur_stop = max(cur_stop, best - trail_d)
                else:
                    best = min(best, lo)
                    if entry_px - best >= be_move:
                        cur_stop = min(cur_stop, entry_px)
                    cur_stop = min(cur_stop, best + trail_d)
                k += 1
        else:
            while k < n_exit and ets[k] <= deadline:
                hi, lo = eh[k], el[k]
                if side == "long":
                    hit_stop, hit_tp = lo <= stop, hi >= tp_lvl
                else:
                    hit_stop, hit_tp = hi >= stop, lo <= tp_lvl
                if hit_stop:
                    exit_px, exit_reason = stop, "stop"; break
                ts = _time_stop(k)
                if ts:
                    exit_px, exit_reason = ts; break
                if hit_tp:
                    exit_px, exit_reason = tp_lvl, "tp"; break
                k += 1
        if exit_px is None:                  # timeout o fin de datos
            k = min(k, n_exit - 1)
            exit_px, exit_reason = float(ec[k]), "timeout"
        exit_ts = int(ets[k])

        taker_exit = exit_reason in ("stop", "timeout", "trail", "time")
        fund = 0.0
        if fund_ts.size:
            m = (fund_ts > T) & (fund_ts <= exit_ts)
            if m.any():
                fund = float(np.sum([p.costs.funding(notional, side, r) for r in fund_rate[m]]))
        pnl, exit_fill = p.costs.realized(side, entry_px, exit_px, notional, entry_fee,
                                          maker_exit=not taker_exit, funding_total=fund)
        R = pnl / risk_amt if risk_amt > 0 else 0.0
        trades.append({
            "sym": sym, "strategy": p.strategy, "side": side,
            "entry_ts": T, "exit_ts": exit_ts, "entry": entry_px, "exit": exit_fill,
            "stop": stop, "tp": tp, "exit_reason": exit_reason,
            "pnl": pnl, "ret": pnl / equity if equity > 0 else 0.0, "R": R,
            "hold_h": (exit_ts - T) / _H,
        })
        equity += pnl
        busy_until_ts = exit_ts              # 1 posición a la vez
    return trades


def backtest_symbol_strat(sym: str, p: StratParams) -> list[dict]:
    """Conveniencia: carga el bundle y corre (para pruebas sueltas)."""
    bundle = load_bundle(sym, p.strategy, p.exit_tf)
    if bundle is None:
        return []
    return run(bundle, p)
