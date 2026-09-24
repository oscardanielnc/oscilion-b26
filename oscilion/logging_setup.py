"""Logging setup: stdout (systemd journal) + rotating file.

Persistent logs in logs/oscilion.log (5 MB x 5). Level comes from config.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR, config

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def setup_logging(level: str | None = None) -> None:
    global _configured
    if _configured:
        return

    lvl = getattr(logging, (level or config.log_level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(lvl)

    fmt = logging.Formatter(_FMT)

    # Keep stdout from crashing on non-ASCII text in cp1252 consoles (Windows).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    fh = RotatingFileHandler(
        LOGS_DIR / "oscilion.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)

    _configured = True
