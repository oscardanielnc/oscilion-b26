"""Notificaciones / alertas (esqueleto Fase 1).

Canal único hoy: log + persistencia en `events`. Si hay credenciales de
Telegram en config, envía también por ahí (best-effort, nunca lanza).
Los 3 momentos de negocio (ENTRA / TOMA GANANCIA / SAL) usarán `notify()`
en fases posteriores sin cambiar esta interfaz.
"""
from __future__ import annotations

import logging

from config import config
from oscilion.persistence import db

log = logging.getLogger(__name__)

_LEVELS = {"INFO", "WARN", "ERROR", "CRITICAL"}


def notify(msg: str, level: str = "INFO", module: str = "notify", extra: dict | None = None) -> None:
    """Registra y, si se puede, despacha una alerta. Best-effort, no lanza."""
    level = level.upper()
    if level not in _LEVELS:
        level = "INFO"

    log.log(_log_level(level), "[ALERT] %s", msg)
    db.log_event(level, module, msg, extra)

    if config.telegram_token and config.telegram_chat_id:
        _send_telegram(f"[{level}] {msg}")


def _log_level(level: str) -> int:
    return {"INFO": logging.INFO, "WARN": logging.WARNING,
            "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}.get(level, logging.INFO)


def _send_telegram(text: str) -> None:
    try:
        import requests

        requests.post(
            f"https://api.telegram.org/bot{config.telegram_token}/sendMessage",
            json={"chat_id": config.telegram_chat_id, "text": text},
            timeout=10,
        )
    except Exception:
        log.exception("No se pudo enviar alerta por Telegram")
