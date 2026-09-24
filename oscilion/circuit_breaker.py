"""Circuit breaker: safety kill-switch for the main loop.

Pauses the whole system after a run of consecutive failed ticks. The daily-loss
brake lives in live/guards.py because it blocks new capital entries without
stopping the management of open positions.

Philosophy: when in doubt, PAUSE. Once tripped it stays tripped until the
service is restarted.
"""
from __future__ import annotations

import logging

from config import config

log = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, max_consecutive_errors: int | None = None) -> None:
        self.max_consecutive_errors = (
            max_consecutive_errors or config.max_consecutive_errors
        )
        self._consecutive_errors = 0
        self._tripped = False
        self._reason: str | None = None

    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def reason(self) -> str | None:
        return self._reason

    def trip(self, reason: str) -> None:
        if not self._tripped:
            self._tripped = True
            self._reason = reason
            log.critical("CIRCUIT BREAKER TRIPPED: %s", reason)

    def record_success(self) -> None:
        self._consecutive_errors = 0

    def record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self.max_consecutive_errors:
            self.trip(
                f"{self._consecutive_errors} consecutive failed ticks "
                f"(limit {self.max_consecutive_errors})"
            )

    def check(self) -> bool:
        """True if it is safe to continue; False if tripped."""
        return not self._tripped
