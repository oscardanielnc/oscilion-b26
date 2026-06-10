"""Guardas de proceso del monitor (FORWARD_REVIEW 2026-06-10, puntos 1, 2 y stale).

Funciones PURAS (sin red ni BD) para que sean testeables y reutilizables.
Filosofía: el edge vive en las estrategias; estas guardas solo impiden operar
lo NO validado, lo duplicado o lo vencido. Cada bloqueo deja rastro (lo loguea
el llamador) — nada se descarta en silencio.
"""
from __future__ import annotations

from config import config


def gate_decision(bt_stats: dict | None, observe_only: bool,
                  *, min_n: int | None = None,
                  min_exp_r: float | None = None) -> tuple[bool, str | None]:
    """Decide si un combo sym×estrategia opera con capital.

    `bt_stats` = fila de forward_results scope='backtest' (motor honesto sobre
    los datos locales): el gate usa la evidencia REAL disponible en esta máquina,
    no números de research que el histórico local quizá no respalda (el caso
    DOGE/vwap n=1 del primer ciclo).

    Devuelve (observe, reason): observe=True → trade virtual SIN capital.
    """
    if observe_only:
        return True, "observe_only (asignación)"
    min_n = config.gate_min_n if min_n is None else min_n
    min_exp_r = config.gate_min_exp_r if min_exp_r is None else min_exp_r
    if not bt_stats:
        return True, "gate: sin backtest local (forward_results vacío)"
    n = int(bt_stats.get("n") or 0)
    exp_r = bt_stats.get("exp_r")
    if n < min_n:
        return True, f"gate: n={n} < {min_n}"
    if exp_r is None or exp_r <= min_exp_r:
        er = "—" if exp_r is None else f"{exp_r:+.3f}"
        return True, f"gate: exp_R={er} ≤ {min_exp_r:+.2f}"
    return False, None


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
