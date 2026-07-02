"""Integridad temporal de trades + fuente REAL del gate (auditoría 2026-07-02).

Dos bugs que este archivo clava para siempre:
  1. `trades.ts` debe ser la APERTURA. El monitor no pasaba `ts` y log_trade
     caía al default _now_ms() = hora del cierre → el análisis por eras/semanas
     atribuía trades a la era equivocada (el PAXG "+4.78R post-v0.8" era de v0.7).
  2. El gate adaptativo (kill/graduación) debe leer el LIBRO REAL, no la
     simulación del motor (scope 'forward'), que divergía (XAU +1.35 sim vs
     −2.47R real).
"""
import sqlite3

import pytest

from oscilion.persistence import db


@pytest.fixture()
def mem_db():
    """BD en memoria aislada; restaura la conexión global al salir."""
    prev = db._conn
    db._conn = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    db._conn.row_factory = sqlite3.Row
    db.init_db()
    yield db
    db._conn.close()
    db._conn = prev


def _trade(mem, sym, strategy, ts, r, observe=0, status="closed"):
    return mem.log_trade(sym, "long", "dry-run", ts=ts, strategy=strategy,
                         r_multiple=r, observe=observe, status=status)


def test_log_trade_respeta_ts_explicito(mem_db):
    tid = _trade(mem_db, "BTC/USDT:USDT", "orb_breakout", ts=1_000_000, r=1.5)
    row = mem_db.get_connection().execute(
        "SELECT ts FROM trades WHERE id=?", (tid,)).fetchone()
    assert row["ts"] == 1_000_000  # apertura, NO la hora del INSERT


def test_real_forward_stats_agrega_ambos_libros(mem_db):
    sym, strat = "XAU/USDT:USDT", "momentum_pullback"
    _trade(mem_db, sym, strat, ts=100, r=-1.2, observe=1)   # observe cuenta
    _trade(mem_db, sym, strat, ts=200, r=+2.0, observe=0)   # capital cuenta
    _trade(mem_db, sym, strat, ts=300, r=+0.4, observe=0)
    _trade(mem_db, sym, "vwap_anchor", ts=200, r=-9.9)      # otra estrategia NO
    s = mem_db.real_forward_stats(sym, strat, since_ms=0)
    assert s["n"] == 3
    assert s["exp_r"] == pytest.approx((-1.2 + 2.0 + 0.4) / 3)
    assert s["win_rate"] == pytest.approx(2 / 3)


def test_real_forward_stats_acota_a_la_era_vigente(mem_db):
    sym, strat = "ETH/USDT:USDT", "vwap_anchor"
    _trade(mem_db, sym, strat, ts=100, r=-1.0)   # era anterior (reglas viejas)
    _trade(mem_db, sym, strat, ts=500, r=+0.5)   # era vigente
    s = mem_db.real_forward_stats(sym, strat, since_ms=400)
    assert s["n"] == 1 and s["exp_r"] == pytest.approx(0.5)


def test_real_forward_stats_none_sin_trades(mem_db):
    assert mem_db.real_forward_stats("NADA/USDT:USDT", "orb_breakout", since_ms=0) is None
