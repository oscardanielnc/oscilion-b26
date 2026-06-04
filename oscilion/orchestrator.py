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

import json
import logging
import os
import signal
import time

from config import DATA_DIR, config
from oscilion import __version__
from oscilion.circuit_breaker import CircuitBreaker
from oscilion.logging_setup import setup_logging
from oscilion.notify import notify
from oscilion.persistence import db
from oscilion.live.monitor import LiveMonitor

log = logging.getLogger("oscilion.orchestrator")

STATE_FILE = DATA_DIR / "state.json"


class Orchestrator:
    def __init__(self) -> None:
        self.breaker = CircuitBreaker()
        self.engine = LiveMonitor()
        self._running = False
        self._tick_count = 0
        self._last_backup_day = None

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
        """Un ciclo del monitor en vivo (Fase 5): refresca datos, avanza la
        máquina de estados por moneda, emite alertas y publica el estado.
        En dry-run/paper NO opera: solo recomienda y registra.
        """
        self._tick_count += 1
        alerts = self.engine.step()
        self._publish_state()
        self._daily_backup()
        # LOGS MÍNIMOS: solo alertas (la señal) a INFO; latido rutinario a DEBUG;
        # un heartbeat horario a INFO para saber que sigue vivo sin saturar.
        if alerts:
            for a in alerts:
                log.info("ALERTA %s", a.get("msg", a))
        elif self._tick_count % 60 == 0:
            log.info("vivo · tick #%d · %d series", self._tick_count, len(self.engine.symbols))
        else:
            log.debug("tick #%d ok | %d alertas", self._tick_count, len(alerts))

    def _daily_backup(self) -> None:
        """Backup de la BD una vez al día (protege el track record forward)."""
        today = time.strftime("%Y-%m-%d")
        if today != self._last_backup_day:
            self._last_backup_day = today
            db.backup_db()

    def _publish_state(self) -> None:
        """Vuelca el estado de las máquinas a data/state.json (lo lee la API)."""
        try:
            snap = {"ts": int(time.time() * 1000), "mode": config.mode.value,
                    "tick": self._tick_count, "symbols": self.engine.snapshot()}
            tmp = STATE_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(snap, default=str), encoding="utf-8")
            os.replace(tmp, STATE_FILE)
        except Exception:
            log.exception("No se pudo publicar state.json")


def main() -> None:
    Orchestrator().run_loop()


if __name__ == "__main__":
    main()
