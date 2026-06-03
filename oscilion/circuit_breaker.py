"""Circuit breaker — kill-switch de seguridad (esqueleto Fase 1).

Pausa todo el sistema ante anomalías: errores en cadena, pérdida diaria
excedida, datos corruptos o desconexión. En Fase 1 solo implementa el conteo
de errores consecutivos y el armazón de la API; los disparadores de mercado
(pérdida diaria, datos raros) se conectan en fases posteriores.

Filosofía: ante la duda, PAUSAR. Reactivar es manual o por reset explícito.
"""
from __future__ import annotations

import logging
import time

from config import config

log = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(
        self,
        max_consecutive_errors: int | None = None,
        max_daily_loss: float | None = None,
    ) -> None:
        self.max_consecutive_errors = (
            max_consecutive_errors or config.max_consecutive_errors
        )
        self.max_daily_loss = max_daily_loss or config.max_daily_loss
        self._consecutive_errors = 0
        self._tripped = False
        self._reason: str | None = None
        self._tripped_at: float | None = None

    # ---- estado ----
    @property
    def tripped(self) -> bool:
        return self._tripped

    @property
    def reason(self) -> str | None:
        return self._reason

    def status(self) -> dict:
        return {
            "tripped": self._tripped,
            "reason": self._reason,
            "consecutive_errors": self._consecutive_errors,
            "tripped_at": self._tripped_at,
        }

    # ---- transiciones ----
    def trip(self, reason: str) -> None:
        if not self._tripped:
            self._tripped = True
            self._reason = reason
            self._tripped_at = time.time()
            log.critical("CIRCUIT BREAKER DISPARADO: %s", reason)

    def reset(self) -> None:
        log.warning("Circuit breaker reseteado (reason previa: %s)", self._reason)
        self._tripped = False
        self._reason = None
        self._tripped_at = None
        self._consecutive_errors = 0

    # ---- señales desde el loop ----
    def record_success(self) -> None:
        self._consecutive_errors = 0

    def record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self.max_consecutive_errors:
            self.trip(
                f"{self._consecutive_errors} ticks fallidos consecutivos "
                f"(límite {self.max_consecutive_errors})"
            )

    def check(self) -> bool:
        """Devuelve True si es seguro continuar; False si está disparado."""
        return not self._tripped
