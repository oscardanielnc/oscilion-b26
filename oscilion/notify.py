"""Notifications / alerts.

Always: log + persistence in `events`. If configured, also pushes to ntfy.sh
and/or Telegram (best-effort, never raises).
"""
from __future__ import annotations

import logging

from config import config
from oscilion.persistence import db

log = logging.getLogger(__name__)

_LEVELS = {"INFO", "WARN", "ERROR", "CRITICAL"}


def notify(msg: str, level: str = "INFO", module: str = "notify", extra: dict | None = None) -> None:
    """Record and, when possible, dispatch an alert. Best-effort, never raises."""
    level = level.upper()
    if level not in _LEVELS:
        level = "INFO"

    log.log(_log_level(level), "[ALERT] %s", msg)
    db.log_event(level, module, msg, extra)

    if config.ntfy_topic:
        _send_ntfy(msg, level)
    if config.telegram_token and config.telegram_chat_id:
        _send_telegram(f"[{level}] {msg}")


def _send_ntfy(text: str, level: str) -> None:
    try:
        import requests

        prio = {"CRITICAL": "5", "ERROR": "4", "WARN": "3"}.get(level, "3")
        requests.post(f"https://ntfy.sh/{config.ntfy_topic}",
                      data=text.encode("utf-8"),
                      headers={"Title": "Oscilion", "Priority": prio},
                      timeout=10)
    except Exception:
        log.exception("Could not send ntfy alert")


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
        log.exception("Could not send Telegram alert")
