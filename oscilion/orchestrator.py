"""Orquestador — loop principal, scheduling y resiliencia (ARCHITECTURE.md §6).

Garantías de Fase 1:
  • Arranca, inicializa DB y registra el set de parámetros (auditoría).
  • Loop infinito: cada `tick()` va en try/except → un fallo loguea y continúa.
  • Circuit breaker cuenta errores consecutivos y puede pausar.
  • Apagado limpio ante SIGINT/SIGTERM (systemd manda SIGTERM).
  • NO opera: la lógica de trading entra en fases posteriores. Hoy el tick
    solo emite un heartbeat y deja rastro persistente.
"""
from __future__ import annotations

import logging
import signal
import time

from config import config
from oscilion import __version__
from oscilion.circuit_breaker import CircuitBreaker
from oscilion.logging_setup import setup_logging
from oscilion.notify import notify
from oscilion.persistence import db

log = logging.getLogger("oscilion.orchestrator")


class Orchestrator:
    def __init__(self) -> None:
        self.breaker = CircuitBreaker()
        self._running = False
        self._tick_count = 0

    # ---------------------------- ciclo de vida ----------------------------
    def startup(self) -> None:
        setup_logging()
        db.init_db()
        db.log_params(config.version, config.as_params())
        log.info(
            "Oscilion v%s arrancando | modo=%s | símbolos=%s | tick=%ss",
            __version__, config.mode.value, ",".join(config.symbols), config.tick_seconds,
        )
        notify(f"Oscilion v{__version__} arrancado (modo {config.mode.value})", "INFO", "orchestrator")
        self._install_signals()

    def _install_signals(self) -> None:
        def _handler(signum, _frame):
            log.info("Señal %s recibida → apagado limpio", signum)
            self._running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass  # p.ej. en un hilo no principal

    def shutdown(self) -> None:
        notify("Oscilion detenido", "INFO", "orchestrator")
        log.info("Apagado tras %d ticks", self._tick_count)
        db.close()

    # ------------------------------- loop ----------------------------------
    def run_loop(self) -> None:
        self.startup()
        self._running = True
        try:
            while self._running:
                started = time.monotonic()

                if self.breaker.check():
                    self._safe_tick()
                else:
                    log.warning("Circuit breaker activo (%s) — tick omitido", self.breaker.reason)

                # dormir lo que reste del intervalo, interrumpible
                elapsed = time.monotonic() - started
                self._sleep(max(0.0, config.tick_seconds - elapsed))
        finally:
            self.shutdown()

    def _safe_tick(self) -> None:
        """Envuelve tick() para que NADA tumbe el servicio."""
        try:
            self.tick()
            self.breaker.record_success()
        except Exception:
            log.exception("Error en tick #%d", self._tick_count)
            db.log_event("ERROR", "orchestrator", f"tick #{self._tick_count} falló")
            self.breaker.record_error()
            if self.breaker.tripped:
                notify(f"Circuit breaker disparado: {self.breaker.reason}", "CRITICAL", "orchestrator")

    def _sleep(self, seconds: float) -> None:
        """Sleep en tramos cortos para responder rápido a las señales."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    # ------------------------------- tick ----------------------------------
    def tick(self) -> None:
        """Un ciclo de trabajo. Fase 1: heartbeat + snapshot vacío por símbolo.

        Aquí se enchufará en orden: fetch de datos → features → scoring →
        risk → señales → ejecución. Por ahora solo demuestra el latido y
        que la persistencia funciona.
        """
        self._tick_count += 1
        for sym in config.symbols:
            db.log_snapshot(sym, price=None, indicators={"phase": 1, "note": "heartbeat"})
        log.info("tick #%d ok | %d símbolos", self._tick_count, len(config.symbols))


def main() -> None:
    Orchestrator().run_loop()


if __name__ == "__main__":
    main()
