# Oscilion - Architecture

> This is the architecture as it was **designed before construction** (sections 1-7).
> Some planned modules were never built because the go/no-go gates stopped the
> project first (live execution, the per-coin state machine, score calibration).
> Section 8 maps the design to the code that actually exists.

## 1. Design principle

**Separate the brain from the arm.** The signal engine decides; the executor trades.
That way we go from monitor -> bot -> copy-lead without rewriting anything.

```
        DATA              BRAIN (signals)                 ARM              OUTPUT
   +-----------+   +---------------------------+   +-----------+   +----------+
   |  Binance  |-->| features -> scoring -> risk|-->| executor  |-->| Binance  |
   |  (ccxt)   |   |   -> signals (state mach.) |   | paper/live|   |  orders  |
   +-----+-----+   +-------------+-------------+   +-----+-----+   +----------+
         |                       |                       |
         v                       v                       v
   +-------------------- PERSISTENCE (append-only, auditable) ----------------+
   |  snapshots - predictions - decisions - trades - params - logs            |
   +----------------------------------+---------------------------------------+
                                      v
                            +--------------------+
                            |  API (FastAPI)     |--> Frontend (React) + Alerts
                            +--------------------+
```

## 2. Folder structure

```
Oscilion/
|-- README.md  requirements.txt  .gitignore
|-- config.py                  # central configuration (env, symbols, thresholds)
|-- deploy.sh                  # 1 command: pull + deps + verify + restart
|-- setup_vm.sh                # initial provisioning on the Oracle VM
|-- oscilion.service           # systemd: orchestrator (Restart=always)
|-- oscilion-api.service       # systemd: API/dashboard
|-- docs/                      # VISION - RISK_MODEL - ARCHITECTURE - ROADMAP
|-- oscilion/                  # main package
|   |-- orchestrator.py        # main loop, scheduling, resilience
|   |-- data/
|   |   |-- fetch.py           # OHLCV + funding from Binance (ccxt)
|   |   |-- store.py           # parquet + DB, no gaps, no look-ahead
|   |   `-- universe.py        # coin universe and its metadata
|   |-- features/
|   |   |-- indicators.py      # ATR, BB, Keltner, VWAP, Donchian, ADX
|   |   |-- ranges.py          # horizontal ranges + diagonal channels
|   |   |-- regime.py          # range vs trend + volatility regime
|   |   `-- reversion.py       # Hurst, OU half-life, variance ratio, ADF
|   |-- scoring/
|   |   |-- conviction.py      # 0-100% score combining features
|   |   `-- calibration.py     # measures whether the score holds up (forward)
|   |-- risk/
|   |   |-- stops.py           # anti-sweep stop (cluster + ATR)
|   |   |-- sizing.py          # L = 2%/stop, position size
|   |   `-- allocation.py      # portfolio weights: kelly + vol + correlation
|   |-- signals/
|   |   |-- state_machine.py   # per-coin state (see section 4)
|   |   |-- entry.py           # edge + turn confirmation
|   |   |-- exit.py            # TP/trailing/stop/adverse breakout
|   |   `-- maker_taker.py     # decides maker vs taker
|   |-- execution/
|   |   |-- broker.py          # common order interface
|   |   |-- paper.py           # paper trading (simulates fills + costs)
|   |   `-- binance.py         # real perpetuals execution (Phase 7)
|   |-- backtest/
|   |   |-- engine.py          # walk-forward, no look-ahead
|   |   |-- costs.py           # fees + funding + slippage
|   |   `-- metrics.py         # Sharpe, DD, MAE/MFE, winrate, calibration
|   |-- persistence/
|   |   |-- db.py              # connection, migrations, append-only
|   |   `-- models.py          # table schema (see section 5)
|   |-- circuit_breaker.py     # safety kill-switch
|   |-- notify.py              # alerts (Telegram/others)
|   `-- api/
|       |-- app.py             # FastAPI: state/history endpoints
|       |-- dashboard.html     # minimal dashboard (before the React frontend)
|       `-- __main__.py
|-- frontend/                  # React + TS + lightweight-charts (Phase 5)
|-- data/                      # parquet + oscilion.db   (gitignored)
|-- logs/                      # persistent logs         (gitignored)
`-- research/                  # notebooks and experiments
```

## 3. Key modules and responsibilities

| Module | Responsibility | Core functions (indicative signature) |
|---|---|---|
| `data/fetch.py` | Download data with no gaps | `fetch_ohlcv(sym, tf, since)` - `fetch_funding(sym)` |
| `data/store.py` | Persist/read clean data | `save_bars()` - `load_bars()` - `gaps_report()` |
| `features/ranges.py` | Horizontal and diagonal range | `horizontal_range(bars)` - `diagonal_channel(bars)` |
| `features/regime.py` | Classify the regime | `classify_regime(bars) -> {range|trend|chaos}` |
| `features/reversion.py` | Reversion quality | `hurst()` - `ou_half_life()` - `variance_ratio()` - `adf()` |
| `scoring/conviction.py` | 0-100 score | `conviction(sym, snapshot) -> {score, components}` |
| `scoring/calibration.py` | Does the score hold up? | `update_calibration()` - `reliability_curve()` |
| `risk/stops.py` | Safe stop | `safe_stop(sym, side, entry, bars)` |
| `risk/sizing.py` | L and size | `leverage(stop_pct)` - `position_size(capital, stop_pct)` |
| `risk/allocation.py` | Portfolio weights | `allocate(candidates, capital) -> weights` |
| `signals/state_machine.py` | Per-coin state | `step(sym, snapshot) -> state` |
| `signals/entry.py` | Entry signal | `entry_signal(sym) -> {enter?, price, conf}` |
| `signals/exit.py` | Exit management | `exit_signal(trade) -> {hold|tp|stop|break}` |
| `execution/broker.py` | Orders (paper/live) | `place()` - `cancel()` - `position()` |
| `backtest/engine.py` | Historical validation | `walk_forward(strategy, period)` |
| `persistence/db.py` | Audit | `log_snapshot()` - `log_prediction()` - `log_decision()` - `log_trade()` |
| `orchestrator.py` | Glue + loop | `run_loop()` - `tick()` |
| `circuit_breaker.py` | Safety | `check()` (pauses everything if something gets out of control) |

## 4. Per-coin state machine

```
   +----------+  price far from the edge
   | WAITING  |<-----------------------------------+
   +----+-----+                                    |
        | price approaches an edge                 | no confirmation / moves away
        v                                          |
   +--------------+   turn confirmed    +----------+-----+
   | APPROACHING  |-------------------->|  CONFIRMING    |
   +--------------+                     +-------+--------+
                                                | turn confirmed + RR>=2.5
                                                v
                                        +----------------+
                                        |  IDEAL ENTRY   | -> "ENTER" alert
                                        +-------+--------+
                                                v
                                        +----------------+
                                        |   IN TRADE     |  (continuous monitoring)
                                        +-------+--------+
              +--------------+------------------+-------------------+
              v              v                  v                   v
          TP reached     momentum fades     stop touched        adverse breakout
          (or trailing)  -> partial profit  -> taker exit       -> urgent taker exit
```

## 5. Data model (append-only, auditable)

| Table | Purpose | Key fields |
|---|---|---|
| `market_snapshots` | Market state on every tick | ts, sym, price, ohlcv_ref, indicators |
| `predictions` | What the system "believed" | ts, sym, score, range (lo, hi), regime, stop, tp, RR |
| `decisions` | What was decided and why | ts, sym, action (enter/wait/no-trade), reason |
| `trades` | Real/paper trades | id, sym, side, entry, stop, tp, exit, pnl, fees, funding, L |
| `params` | Configuration in use | ts, version, json_params (to reproduce) |
| `calibration` | Predicted score vs outcome | bucket_score, n, hits, real_ratio |
| `events/logs` | Errors, restarts, alerts | ts, level, module, msg |

> Rule: nothing is ever overwritten or deleted. This provides: history for the
> frontend, material to improve, calibration measurement and an **honest forward
> test** = the track record for copy-lead.

## 6. Operations and resilience

- **systemd**: `oscilion.service` (orchestrator) + `oscilion-api.service`
  (dashboard). `Restart=always`, `RestartSec=30`. Logs to the journal **and** to
  `logs/`.
- **Never die**: every `tick()` is wrapped in try/except -> log and continue. An
  error on one coin does not bring the system down.
- **Circuit breaker**: if something gets out of control (odd data, chained losses,
  disconnection) -> safe pause and alert.
- **One-command `deploy.sh`** (on the VM): `git pull` -> `pip install` -> import
  check -> `systemctl restart` of both services -> status summary. Same pattern as
  the other services on that VM.
- **`setup_vm.sh`**: initial provisioning (venv, env file, services) the first time.
- **Per-environment config**: `EnvironmentFile=/etc/oscilion.env` (API keys,
  dry-run/demo mode). No secrets in git.
- **Modes**: `dry-run` (no trading), `paper` (simulated), `live` (real). Always
  starts in the safest mode.

## 7. Frontend (Phase 5)

React + TS + **lightweight-charts**. Views: candidate ranking with score, dynamic
range + stop + TP per coin, state machine status, open positions, auditable
history, equity curve and calibration. It reads from the API; the API reads from the
DB. Push alerts for the 3 moments: **ENTER / TAKE PROFIT / EXIT**.

## 8. As built (what the code actually contains)

The range-reversion design above was built and backtested (phases 1-4). When the
validation rejected it, the live layer was rebuilt around the directional
strategies that did pass the backtest (see `docs/FINDINGS.md` and
`docs/STRATEGY_MAP.md`). The repository reflects that:

| Planned | Built |
|---|---|
| `features/`, `scoring/conviction.py`, `risk/`, `signals/entry.py`, `backtest/engine.py` | Built as designed. Used by the range-reversion research path (`analysis.py`, `backtest/engine.py`, `research/edge_campaign.py`). A smoke test enforces that production never imports them. |
| `signals/state_machine.py`, `signals/exit.py` | Not built as separate modules. The live state (waiting / signal active / in trade) and exit management live in `live/monitor.py`. |
| Directional strategies (not in the original plan) | `strategies/library.py` (5 pure signal functions), `strategies/assignment.py` (coin -> strategy map), `strategies/portfolio.py` + `tuned.py` (weights, clusters, limits), `backtest/engine_strat.py` (honest engine with 15m pessimistic exits). |
| Validation gate (not in the original plan) | `live/guards.py` + `live/forward.py`: backtest/forward gate, kill-switch, graduation, market-regime filter, cost filter, portfolio limits, daily loss brake. |
| `scoring/calibration.py`, `calibration` table | Not built. Calibration is measured offline by `backtest/metrics.calibration`; the table exists in the schema but nothing writes to it. |
| `market_snapshots` table | Exists in the schema but nothing writes to it. The per-cycle audit trail is `series_snapshots` (written by the monitor). |
| `execution/` (broker, paper, Binance) | Not built. The system only ever ran in dry-run: virtual trades are recorded with real cost modeling, no orders are placed. |
| `api/dashboard.html` | Replaced by the React dashboard in `frontend/` (served by the API at `/`). |
| `frontend/` with lightweight-charts | Built with React + TS + Vite, tables only (no charting library). |
| Data model | `persistence/models.py`: `predictions`, `decisions`, `trades`, `params`, `events`, `forward_results`, `ohlcv_status`, `monitor_state`, `series_snapshots`, `schema_meta` (+ the two unused tables above). Schema v6 with idempotent migrations. |
