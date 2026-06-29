"""Guardas de proceso del monitor (FORWARD_REVIEW 2026-06-10, puntos 1, 2 y stale).

Funciones PURAS (sin red ni BD) para que sean testeables y reutilizables.
Filosofía: el edge vive en las estrategias; estas guardas solo impiden operar
lo NO validado, lo duplicado o lo vencido. Cada bloqueo deja rastro (lo loguea
el llamador) — nada se descarta en silencio.
"""
from __future__ import annotations

from config import config


def _ev(stats: dict | None) -> tuple[int, float | None]:
    """(n, exp_r) tolerante a None."""
    if not stats:
        return 0, None
    return int(stats.get("n") or 0), stats.get("exp_r")


def gate_decision(bt_stats: dict | None, observe_only: bool,
                  *, fw_stats: dict | None = None,
                  sub_windows: list[dict | None] | None = None,
                  min_n: int | None = None, min_exp_r: float | None = None,
                  fw_kill_n: int | None = None, fw_kill_exp_r: float | None = None,
                  fw_grad_n: int | None = None, fw_grad_exp_r: float | None = None,
                  robust: bool | None = None,
                  robust_min_n: int | None = None) -> tuple[bool, str | None]:
    """Decide si un combo sym×estrategia opera con capital.

    `bt_stats` = fila de forward_results scope='backtest' (motor honesto, OOS):
    evidencia local, no números de research que el histórico local quizá no
    respalda (el caso DOGE/vwap n=1 del primer ciclo).
    `fw_stats` = scope='forward' (OOS post-inception, con filtros de régimen/costo):
    el EDGE REAL reciente. Cierra el lazo que faltaba (auditoría 06-29: observe le
    ganaba a capital porque el gate nunca miraba el forward).

    Prioridad: forward real (kill/graduación) MANDA sobre el backtest, porque mide
    cómo opera el combo HOY. Sin muestra forward suficiente, decide el backtest.

    Devuelve (observe, reason): observe=True → trade virtual SIN capital.
    """
    min_n = config.gate_min_n if min_n is None else min_n
    min_exp_r = config.gate_min_exp_r if min_exp_r is None else min_exp_r
    fw_kill_n = config.gate_fw_kill_n if fw_kill_n is None else fw_kill_n
    fw_kill_exp_r = config.gate_fw_kill_exp_r if fw_kill_exp_r is None else fw_kill_exp_r
    fw_grad_n = config.gate_fw_grad_n if fw_grad_n is None else fw_grad_n
    fw_grad_exp_r = config.gate_fw_grad_exp_r if fw_grad_exp_r is None else fw_grad_exp_r
    robust = config.gate_robust if robust is None else robust
    robust_min_n = config.gate_robust_min_n if robust_min_n is None else robust_min_n

    fw_n, fw_exp = _ev(fw_stats)

    if observe_only:
        # GRADUACIÓN: el forward real confirma edge con holgura → sube a capital.
        if fw_n >= fw_grad_n and fw_exp is not None and fw_exp >= fw_grad_exp_r:
            return False, None
        return True, "observe_only (asignación)"

    # KILL-SWITCH: el forward real ya demostró que el combo sangra → corta capital.
    if fw_n >= fw_kill_n and fw_exp is not None and fw_exp <= fw_kill_exp_r:
        return True, f"forward kill: exp_R={fw_exp:+.3f} (n={fw_n}) ≤ {fw_kill_exp_r:+.2f}"

    # gate de backtest (OOS) — el filtro base cuando el forward aún no es decisivo.
    if not bt_stats:
        return True, "gate: sin backtest local (forward_results vacío)"
    n, exp_r = _ev(bt_stats)
    if n < min_n:
        return True, f"gate: n={n} < {min_n}"
    if exp_r is None or exp_r <= min_exp_r:
        er = "—" if exp_r is None else f"{exp_r:+.3f}"
        return True, f"gate: exp_R={er} ≤ {min_exp_r:+.2f}"
    # robustez RECENCY-AWARE: la ventana OOS MÁS RECIENTE (sub_windows[-1]) no puede
    # estar decayendo. Bloquea el caso peligroso (+0.30 viejo / −0.20 reciente = edge
    # que se apaga) PERO permite el alpha EMERGENTE/regime-específico (−0.20 viejo /
    # +1.07 reciente), que es la tesis del proyecto (break_retest gana cuando los alts
    # caen, fenómeno reciente). Promediar ambas o exigir las dos positivas lo mataría.
    if robust and sub_windows:
        wn, wexp = _ev(sub_windows[-1])
        if wn >= robust_min_n and (wexp is None or wexp <= min_exp_r):
            we = "—" if wexp is None else f"{wexp:+.3f}"
            return True, f"gate robusto: OOS reciente exp_R={we} ≤ {min_exp_r:+.2f} (n={wn}) — edge decae"
    return False, None


def market_regime_block(side: str, market_bull: bool | None, *,
                        enabled: bool = True, exempt: bool = False) -> str | None:
    """Beta-filtro de régimen: no operar A FAVOR de la beta cuando el mercado base
    va EN CONTRA del lado del trade. Largo de continuación con mercado bajista =
    trampa alcista (las 17 vwap de la auditoría 06-29); short con mercado alcista,
    simétrico. Devuelve la razón del bloqueo, o None si la entrada está permitida.

    `market_bull` None ⇒ régimen desconocido (sin datos) → no bloquea (fail-open).
    `exempt` True ⇒ activo descorrelacionado del benchmark (oro) → no aplica.
    """
    if not enabled or exempt or market_bull is None:
        return None
    if side == "long" and not market_bull:
        return "mercado bajista (benchmark<EMA) contra LONG"
    if side == "short" and market_bull:
        return "mercado alcista (benchmark>EMA) contra SHORT"
    return None


def is_fresh(sig_close_ms: int, now_ms: int, max_age_min: int | None = None) -> bool:
    """True si la vela de señal cerró hace poco. Una señal vieja (downtime,
    refresh fallido) entraría a un precio de referencia vencido — y puede
    saltarse filtros de sesión evaluados con la hora de la VELA, no la actual."""
    max_age = (config.max_signal_age_min if max_age_min is None else max_age_min) * 60_000
    return (now_ms - sig_close_ms) <= max_age


def stop_pct_ok(stop_pct: float, min_stop_pct: float | None = None) -> bool:
    """Piso de distancia de stop: riesgo fijo / stop→0 = notional absurdo."""
    floor = config.min_stop_pct if min_stop_pct is None else min_stop_pct
    return stop_pct >= floor


def cluster_cap_reason(open_combos: list[tuple[str, str]], new_sym: str, new_strategy: str,
                       cluster_of, max_concurrent: int, max_per_cluster: int) -> str | None:
    """Límites de cartera de Fase B (tuned.py: maxc=3, clúster=2) — el esquema con
    el que se VALIDÓ el portfolio. Sin esto el vivo puede cargar 7×2% = 14% de
    riesgo simultáneo en un clúster ~0.7 correlacionado.

    `open_combos` = [(sym, strategy)] de posiciones CON CAPITAL abiertas.
    Devuelve la razón del bloqueo o None si cabe.
    """
    if len(open_combos) >= max_concurrent:
        return f"max_concurrent {len(open_combos)}/{max_concurrent}"
    cl = cluster_of(new_sym, new_strategy)
    n_cl = sum(1 for s, strat in open_combos if cluster_of(s, strat) == cl)
    if n_cl >= max_per_cluster:
        return f"clúster '{cl}' {n_cl}/{max_per_cluster}"
    return None


def utc_midnight_ms(now_ms: int) -> int:
    """00:00 UTC del día de `now_ms` — el freno diario resetea con el día UTC."""
    return (now_ms // 86_400_000) * 86_400_000


def daily_loss_hit(pnl_today: float, capital: float,
                   max_daily_loss: float | None = None) -> bool:
    """True si el PnL cerrado de hoy ya quemó el límite diario (−6% por defecto).
    Solo bloquea nuevas entradas con capital; las abiertas se siguen gestionando."""
    lim = config.max_daily_loss if max_daily_loss is None else max_daily_loss
    return pnl_today <= -lim * capital


def capital_position_on_symbol(states: dict, sym: str) -> str | None:
    """Estrategia con posición CON CAPITAL abierta en `sym` (o None).

    Veto cruzado: 1 posición con capital por símbolo, cualquier dirección —
    misma dirección dobla la apuesta; opuesta paga doble coste para quedar flat.
    Posiciones observe no bloquean (no llevan capital). Posiciones de formato
    previo sin flag `observe` cuentan como capital (conservador).
    """
    for (s, strat), st in states.items():
        pos = getattr(st, "position", None)
        if s == sym and pos is not None and not pos.get("observe", False):
            return strat
    return None
