# Oscilion

Oscilion was built to answer one question with evidence: **can any of these intraday
strategies on Binance USDT perpetuals make money after real costs?** It started as a
range-reversion bot: it detects coins oscillating inside a horizontal range or a clean
diagonal channel, waits for price to reach an edge, requires a **turn confirmation**
(a closed candle reversing with momentum) before entering, targets the opposite edge, and
places the stop beyond the liquidity cluster plus an ATR buffer. When the data rejected
that thesis it pivoted to a set of directional strategies, and those were run live in
dry-run for eight weeks. The answer was no. The project was closed at v1.0, and the
go/no-go criteria that had been written before any code are what closed it.

## Status

**Closed (2026-08-03). No real capital was ever traded.**

| Phase | What | State |
|---|---|---|
| 1 | Base: config, append-only persistence, resilient orchestrator, systemd deploy | Built |
| 2 | Data: OHLCV + funding from Binance, no look-ahead, gap audit | Built |
| 3 | Analysis: ranges, regime, mean-reversion stats, conviction score, risk sizing | Built |
| 4 | Honest backtest: walk-forward, real costs, go/no-go report | Built |
| 5 | Live engine: dry-run monitor, alerts, forward validation | Built (rebuilt for the pivot) |
| 6 | Frontend: React dashboard served by the API | Built |
| 7-9 | Paper trading, live execution, copy-lead | Never built: the go/no-go gate said no |

The live monitor was deployed on an Oracle VM on 2026-06-03 and stopped on 2026-08-03;
the forward sample used for the verdict covers 2026-06-08 to 2026-08-02.
The code, the research scripts and the decision records are all here; the market data
and the SQLite database are not (they are gitignored and can be regenerated).

## The result, and its limits

The headline number from the early work is a Sharpe ratio that went from **-0.47 to +1.89**
when turn confirmation was added to the reversion entry, on **1h candles over about 120
days** of BTC (winrate 28% -> 40%, profit factor 0.87 -> 1.22). **That result was never
confirmed.** It came from a single short window, it still failed the project's own
go/no-go bar (PF 1.22 < 1.3), and the roadmap recorded it at the time as "promising, not
confirmed, multi-year validation pending." It is reported here because it is the kind of
number that makes a project look good, and it did not survive.

What the multi-year validation and the forward test showed:

1. **Three years, 12 coins, net of costs** (`research/edge_campaign.py`): every
   reversion configuration lost money (PF 0.72-0.78), all 12 symbols were negative, and
   the conviction score was *inversely* calibrated (higher score, worse winrate). The same
   campaign on 15m candles was worse. The 1.89 Sharpe was sample luck. Re-running the
   backtest with turn confirmation on BTC alone over 2023-06 to 2026-06 gives PF 0.78 and
   a Sharpe of -0.94.
2. **The pivot.** A momentum/breakout probe showed the right structure (monotonic
   calibration, strong breakouts positive out of sample), and five directional strategies
   ported from an earlier project passed per-coin walk-forward and double out-of-sample
   checks. They were deployed in dry-run with a validation gate, a market-regime filter, a
   cost filter and portfolio limits.
3. **Forward test, 110 trades over 7.8 weeks** (`docs/AUDIT_2026-08-03.md`): **-64.2R**,
   14.5% winrate against a 31.4% breakeven, 18 consecutive losers, in a sideways market
   that was the thesis's most favorable regime. A Monte Carlo puts the probability of this
   under a breakeven system below 1e-4. Four strategies were discarded on decisive evidence
   and the fifth was inconclusive.
4. **The finding that closed the project:** the correlation between each combo's backtest
   expectancy and its forward expectancy was zero to negative (Spearman -0.04 to -0.22).
   Of 22 combos positive in the most recent out-of-sample window, 2 were positive live.
   The problem was not five bad strategies; it was a selection method that picked noise.

Limits of these conclusions: the forward sample is 110 trades, which is decisive in
aggregate but far too small to judge any single coin/strategy pair (that would take years
per pair, as the audit computes). Results depend on the cost model in
`oscilion/backtest/costs.py` (taker fee 0.036%, 2 bps slippage, real funding). Everything
was measured in R in dry-run; no live fills were observed.

## Risk model

Every trade risks a fixed **2% of the capital allocated to that trade**, and leverage is
derived from the stop instead of chosen by hand:

```
leverage = 2% / stop_distance(%)
loss at stop   = 2% of margin, always
gain at target = 2% x RR   (entry filter: RR >= 2.5, so the target is >= +5%)
```

Because the stop sits at 2% of the way to liquidation, liquidation is roughly 50x further
away than the stop. The stop is **anti-sweep**: it goes beyond the recent swing/liquidity
cluster plus an ATR buffer, never at the obvious level where stops get hunted; if that
pushes it further out, leverage drops and the loss stays at 2%. The live layer added a
stop-distance floor, a cost filter, one capital position per symbol, per-cluster limits
and a -6% daily loss brake. Full derivation and examples: [docs/RISK_MODEL.md](docs/RISK_MODEL.md).

## Architecture

The signal logic is shared by the backtest and the live monitor, so what gets validated is
what trades. Everything the system decides is written append-only to SQLite.

```
Binance (ccxt) -> data/ (parquet + ohlcv_status)
                     |
      +--------------+-----------------------------+
      |                                            |
 research path (range reversion)            production path (directional pilot)
 features/ -> scoring/ -> risk/             strategies/ (library, assignment, tuned)
 analysis.py, backtest/engine.py            backtest/engine_strat.py (honest engine)
 research/*.py                              live/ (monitor, guards, forward, signals)
                                                   |
                         persistence/ (SQLite WAL, append-only, schema v6)
                                                   |
                               api/ (FastAPI) -> frontend/ (React + TS)
```

| Package | Responsibility |
|---|---|
| `oscilion/data` | OHLCV/funding download with no look-ahead (the forming candle is dropped), parquet storage, gap/dupe audit, backfill CLI |
| `oscilion/features` | Indicators, horizontal range and regression channel, range/trend/chaos regime, Hurst/OU half-life/variance ratio/ADF, BTC market regime |
| `oscilion/scoring`, `risk`, `signals`, `analysis.py` | The original range-reversion signal: 0-100 conviction score, anti-sweep stop, `L = 2%/stop` sizing, allocation, turn confirmation |
| `oscilion/backtest` | `engine.py` (reversion walk-forward), `engine_strat.py` (directional strategies, pessimistic 15m exits), shared cost model, metrics, go/no-go report, single-account portfolio simulator |
| `oscilion/strategies` | Five pure directional signal functions, the coin -> strategy map, weights/clusters/limits |
| `oscilion/live` | Dry-run monitor (virtual trades with full cost accounting, state survives restarts), pure guard functions, backtest-vs-forward snapshots, daily export |
| `oscilion/persistence` | SQLite schema and idempotent migrations; defensive writes that never take the loop down |
| `oscilion/orchestrator.py`, `circuit_breaker.py` | 24/7 loop with per-tick isolation, circuit breaker on consecutive failures, daily DB backup |
| `oscilion/api`, `frontend/` | Read-only FastAPI endpoints and the dashboard (the built `frontend/dist` is committed and served at `/`) |
| `research/` | The scripts behind every decision in `docs/` (campaigns, OOS checks, purged walk-forward, universe scans) |

A smoke test enforces that the production path never imports the research-only modules.
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the original design and an "as built"
section that maps it to this code.

## Running it locally

Requires Python 3.10+. Node is only needed to rebuild the dashboard.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp example.env .env                  # optional; every variable has a default

python -m pytest -q                  # 41 tests, no network or DB needed

# Market data from Binance's public API (no keys required). 3 years takes a few minutes.
python -m oscilion.data sync --days 1095
python -m oscilion.data report

# Range-reversion backtest (the original thesis) and the go/no-go report
python -m oscilion.backtest --symbols BTC/USDT:USDT --confirm
python -m oscilion.analysis --no-persist           # current candidate ranking

# Directional pilot: backtest vs forward table, live monitor, dashboard
python -m oscilion.live.forward --recompute
python -m oscilion                                  # dry-run monitor loop (Ctrl+C to stop)
python -m oscilion.api                              # http://127.0.0.1:8787

# Research scripts (examples)
python -m research.edge_campaign --tf 1h
python -m research.purged_wf
```

Note on `oscilion.live.forward` run locally: without the VM's deployment date
(`OSCILION_FORWARD_INCEPTION_MS`), its "FORWARD" column is the honest engine *simulated*
over a 2026 holdout, and several combos show positive numbers there. That is exactly the
kind of backtest figure that failed to predict the real forward book (-64.2R); the live
results are only in the audit, because the VM database is not part of the repository.

Reports are written to `data/reports/`. The dashboard in dev mode: `cd frontend && npm
install && npm run dev` (it talks to the API on port 8787). Deployment to a VM with
systemd is described in [docs/DEPLOY.md](docs/DEPLOY.md).

## Documents

| Document | What it covers |
|---|---|
| [VISION](docs/VISION.md) | The original thesis, principles and the go/no-go gate written before building. |
| [RISK_MODEL](docs/RISK_MODEL.md) | The 2% risk math, leverage from the stop, RR filter, anti-sweep stops, sizing, maker vs taker. |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | The planned design, the data model, operations, and what was actually built. |
| [ROADMAP](docs/ROADMAP.md) | The nine phases, the verdicts recorded along the way, and the final status. |
| [FINDINGS](docs/FINDINGS.md) | The 3-year validation that rejected reversion and the momentum/breakout pivot. |
| [BTC_SALVAGE](docs/BTC_SALVAGE.md) | What was reused from an earlier research project and the hypotheses it produced. |
| [VALIDATION_R1_R2](docs/VALIDATION_R1_R2.md) | Honest per-coin validation of the first ported strategies. |
| [STRATEGY_MAP](docs/STRATEGY_MAP.md) | Which strategy worked on which coin in backtest, and why per-coin mattered. |
| [B_PORTFOLIO_PLAN](docs/B_PORTFOLIO_PLAN.md) | Portfolio construction: weights, correlation clusters, limits, and the overfitting it avoided. |
| [DEPLOY](docs/DEPLOY.md) | Step-by-step VM deployment with systemd and the one-command update script. |
| [FORWARD_REVIEW](docs/FORWARD_REVIEW.md) | The first live cycles and the process guards they led to. |
| [AUDIT_2026-06-22](docs/AUDIT_2026-06-22.md) | Mid-test audit and portfolio rebuild (its conclusion was later invalidated). |
| [PROJECT_STATE](docs/PROJECT_STATE.md) | Version-by-version state from v0.7 to the v1.0 closure. |
| [AUDIT_2026-08-03](docs/AUDIT_2026-08-03.md) | The final audit: forward results, statistics, and why the project was closed. |

## Disclaimer

This is an educational and research project. It is not financial advice, it is not a
trading product, and nothing in it should be used to trade real money. Its own conclusion
is that the strategies it contains do not have an edge.
