"""Trade time integrity + the REAL source of the gate (audit 2026-07-02).

Two bugs this file pins down for good:
  1. `trades.ts` must be the OPEN time. The monitor did not pass `ts` and
     log_trade fell back to _now_ms() = close time, so the per-era/per-week
     analysis attributed trades to the wrong era (the "+4.78R post-v0.8" PAXG
     trade was from v0.7).
  2. The adaptive gate (kill/graduation) must read the REAL book, not the engine
     simulation (scope 'forward'), which diverged (XAU +1.35 simulated vs -2.47R
     real).
"""
import sqlite3

import pytest

from oscilion.persistence import db


@pytest.fixture()
def mem_db():
    """Isolated in-memory DB; restores the global connection afterwards."""
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


def test_log_trade_keeps_explicit_ts(mem_db):
    tid = _trade(mem_db, "BTC/USDT:USDT", "orb_breakout", ts=1_000_000, r=1.5)
    row = mem_db.get_connection().execute(
        "SELECT ts FROM trades WHERE id=?", (tid,)).fetchone()
    assert row["ts"] == 1_000_000  # open time, NOT the INSERT time


def test_real_forward_stats_aggregates_both_books(mem_db):
    sym, strat = "XAU/USDT:USDT", "momentum_pullback"
    _trade(mem_db, sym, strat, ts=100, r=-1.2, observe=1)   # observe counts
    _trade(mem_db, sym, strat, ts=200, r=+2.0, observe=0)   # capital counts
    _trade(mem_db, sym, strat, ts=300, r=+0.4, observe=0)
    _trade(mem_db, sym, "vwap_anchor", ts=200, r=-9.9)      # another strategy does NOT
    s = mem_db.real_forward_stats(sym, strat, since_ms=0)
    assert s["n"] == 3
    assert s["exp_r"] == pytest.approx((-1.2 + 2.0 + 0.4) / 3)
    assert s["win_rate"] == pytest.approx(2 / 3)


def test_real_forward_stats_limited_to_current_era(mem_db):
    sym, strat = "ETH/USDT:USDT", "vwap_anchor"
    _trade(mem_db, sym, strat, ts=100, r=-1.0)   # previous era (old rules)
    _trade(mem_db, sym, strat, ts=500, r=+0.5)   # current era
    s = mem_db.real_forward_stats(sym, strat, since_ms=400)
    assert s["n"] == 1 and s["exp_r"] == pytest.approx(0.5)


def test_real_forward_stats_none_without_trades(mem_db):
    assert mem_db.real_forward_stats("NONE/USDT:USDT", "orb_breakout", since_ms=0) is None
