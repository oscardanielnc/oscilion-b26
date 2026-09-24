"""Orchestrator: main loop, scheduling and resilience (ARCHITECTURE.md section 6).

Guarantees:
  - On startup, initializes the DB and records the parameter set (audit).
  - Infinite loop: every `tick()` runs inside try/except, so a failure is logged
    and the loop continues.
  - The circuit breaker counts consecutive failures and can pause the loop.
  - Clean shutdown on SIGINT/SIGTERM (systemd sends SIGTERM).
  - Never places orders: in dry-run/paper it only recommends and records.
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

    # ------------------------------ lifecycle ------------------------------
    def startup(self) -> None:
        setup_logging()
        db.init_db()
        db.log_params(config.version, config.as_params())
        log.info(
            "Oscilion v%s starting | mode=%s | symbols=%s | tick=%ss",
            __version__, config.mode.value, ",".join(config.symbols), config.tick_seconds,
        )
        notify(f"Oscilion v{__version__} started (mode {config.mode.value})", "INFO", "orchestrator")
        self._install_signals()

    def _install_signals(self) -> None:
        def _handler(signum, _frame):
            log.info("Signal %s received, shutting down cleanly", signum)
            self._running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass  # e.g. not on the main thread

    def shutdown(self) -> None:
        notify("Oscilion stopped", "INFO", "orchestrator")
        log.info("Stopped after %d ticks", self._tick_count)
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
                    log.warning("Circuit breaker active (%s), tick skipped", self.breaker.reason)

                elapsed = time.monotonic() - started
                if elapsed > config.tick_seconds:
                    # Slow network or heavy DB. Also persisted so the dashboard shows it.
                    log.warning("slow tick: %.1fs > %ds", elapsed, config.tick_seconds)
                    db.log_event("WARN", "orchestrator",
                                 f"slow tick: {elapsed:.1f}s > {config.tick_seconds}s")
                self._sleep(max(0.0, config.tick_seconds - elapsed))
        finally:
            self.shutdown()

    def _safe_tick(self) -> None:
        """Wrap tick() so that nothing can bring the service down."""
        try:
            self.tick()
            self.breaker.record_success()
        except Exception:
            log.exception("Error in tick #%d", self._tick_count)
            db.log_event("ERROR", "orchestrator", f"tick #{self._tick_count} failed")
            self.breaker.record_error()
            if self.breaker.tripped:
                notify(f"Circuit breaker tripped: {self.breaker.reason}", "CRITICAL", "orchestrator")

    def _sleep(self, seconds: float) -> None:
        """Sleep in short slices so OS signals are handled promptly."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(1.0, end - time.monotonic()))

    # ------------------------------- tick ----------------------------------
    def tick(self) -> None:
        """One live-monitor cycle: refresh data, advance each symbol's state
        machine, emit alerts and publish the state.
        """
        self._tick_count += 1
        alerts = self.engine.step()
        self._publish_state()
        self._daily_backup()
        # Minimal logs: alerts at INFO, routine ticks at DEBUG, plus an hourly
        # INFO heartbeat to prove liveness without flooding the log.
        if alerts:
            for a in alerts:
                log.info("ALERT %s", a.get("msg", a))
        elif self._tick_count % 60 == 0:
            log.info("alive | tick #%d | %d series", self._tick_count, len(self.engine.symbols))
        else:
            log.debug("tick #%d ok | %d alerts", self._tick_count, len(alerts))

    def _daily_backup(self) -> None:
        """Back up the DB once a day (protects the forward track record)."""
        today = time.strftime("%Y-%m-%d")
        if today != self._last_backup_day:
            self._last_backup_day = today
            db.backup_db()

    def _publish_state(self) -> None:
        """Dump the state machines to data/state.json (read by the API)."""
        try:
            snap = {"ts": int(time.time() * 1000), "mode": config.mode.value,
                    "tick": self._tick_count, "symbols": self.engine.snapshot()}
            tmp = STATE_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(snap, default=str), encoding="utf-8")
            os.replace(tmp, STATE_FILE)
        except Exception:
            log.exception("Could not publish state.json")


def main() -> None:
    Orchestrator().run_loop()


if __name__ == "__main__":
    main()
