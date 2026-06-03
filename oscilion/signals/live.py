"""Motor en vivo (Fase 5): conduce una máquina de estados por símbolo.

Cada tick: refresca datos recientes (incremental, sin look-ahead — solo velas
cerradas), avanza cada máquina y recoge alertas. En dry-run recomienda y
registra todo SIN operar. Reusa fetch (F2) + señal (F3) + máquina (F5).
"""
from __future__ import annotations

import logging

from config import config
from oscilion.data import fetch, store
from oscilion.signals.state_machine import SymbolStateMachine

log = logging.getLogger(__name__)


class LiveEngine:
    def __init__(self, symbols: list[str] | None = None, tf: str | None = None, *,
                 capital: float = 10_000.0, refresh: bool = True):
        self.symbols = symbols or config.symbols
        self.tf = tf or config.base_timeframe
        self.refresh = refresh
        self.machines = {s: SymbolStateMachine(s, self.tf, capital=capital) for s in self.symbols}

    def _refresh(self, sym: str) -> None:
        """Trae las velas recientes y las fusiona (idempotente)."""
        tf_ms = fetch.timeframe_to_ms(self.tf)
        since = fetch._now_ms() - 400 * tf_ms
        df = fetch.fetch_ohlcv(sym, self.tf, since=since)
        if not df.empty:
            store.save_bars(sym, self.tf, df)

    def step_all(self) -> list[dict]:
        alerts: list[dict] = []
        for sym, machine in self.machines.items():
            try:
                if self.refresh:
                    self._refresh(sym)
                df = store.load_bars(sym, self.tf)
                alerts.extend(machine.step(df))
            except Exception:
                log.exception("Fallo en máquina de %s", sym)
        return alerts

    def snapshot(self) -> list[dict]:
        return [m.snapshot() for m in self.machines.values()]
