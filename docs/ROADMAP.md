# Oscilion - Phased roadmap

Each phase is self-contained and built in a dedicated session. The order is designed
so that **the system tells the truth as early as possible** (data -> backtest) before
investing in the pretty part (frontend) or the risky part (real money).

```
P1 - Base/infra --> P2 - Data --> P3 - Analysis engine --> P4 - Backtest --> GO/NO-GO
                                                                                 |
   P5 - Live engine --> P6 - Frontend --> P7 - Paper --> P8 - Auto --> P9 - Copy-lead
```

---

## Phase 1 - System base
**Goal:** a solid, resilient, deployable skeleton.
- Folder structure and the `oscilion/` package.
- `config.py`, `requirements.txt`, `.gitignore`, venv.
- `persistence/db.py` + `models.py`: full schema (ARCHITECTURE section 5), append-only.
- `orchestrator.py` with a resilient loop (try/except per tick, logging).
- `circuit_breaker.py` skeleton, `notify.py` skeleton.
- `deploy.sh`, `setup_vm.sh`, `oscilion.service`, `oscilion-api.service`.
- **Deliverable:** a service that starts, logs, persists and restarts itself (no
  trading logic yet).

## Phase 2 - Data
**Goal:** perfect data, no look-ahead.
- `data/fetch.py`: multi-TF OHLCV (1h base, 15m) + historical funding (ccxt/Binance).
- `data/store.py`: parquet + DB, gap detection, cleaning.
- `data/universe.py`: coin universe + metadata (vol, liquidity).
- **Deliverable:** downloaded and audited history for BTC/ETH/SOL + others; a quality
  report.

## Phase 3 - Analysis engine
**Goal:** turn price into measurable signals (real time, rolling window).
- `features/`: indicators, ranges (horizontal + diagonal), regime, reversion
  (Hurst/OU/VR/ADF).
- `scoring/conviction.py`: 0-100 score per coin.
- `risk/`: `stops.py` (anti-sweep), `sizing.py` (L = 2%/stop), `allocation.py`
  (portfolio).
- **Deliverable:** at any given instant, a ranking of candidates with range, stop,
  TP, L and % of capital.

## Phase 4 - Honest backtest
**Goal:** is there an edge after costs? The moment of truth.
- `backtest/engine.py`: walk-forward, no look-ahead.
- `backtest/costs.py`: real fees + funding + slippage.
- `backtest/metrics.py`: Sharpe, max DD, winrate, MAE/MFE, **calibration**.
- **Deliverable:** a go/no-go report with net metrics per coin/regime.

## Phase 5 - Live engine
**Goal:** the brain running 24/7.
- `signals/state_machine.py`, `entry.py`, `exit.py`, `maker_taker.py`.
- `scoring/calibration.py`: real forward test (prediction vs outcome).
- Alerts: ENTER / TAKE PROFIT / EXIT.
- **Deliverable:** a live monitor that recommends and records everything (without
  trading).

## Phase 6 - Frontend
**Goal:** see the ranges and stops dynamically (the value for the user).
- FastAPI API + React/TS + lightweight-charts.
- Ranking, range/stop/TP per coin, state, positions, history, equity, calibration.
- **Deliverable:** a live dashboard.

## Phase 7 - Paper trading
**Goal:** validate live without money.
- `execution/paper.py`: simulates fills + costs in real time.
- Compare paper vs backtest (are they consistent?).
- **Deliverable:** an auditable paper track record.

## Phase 8 - Auto-execution
**Goal:** trade on its own, with small capital.
- `execution/binance.py`: real perpetuals orders, post-only/maker-taker, stop
  management.
- A serious circuit breaker, hard limits.
- **Deliverable:** a bot trading for real, supervised, scaling gradually.

## Phase 9 - Copy-lead
**Goal:** monetize through copier commissions.
- A verifiable track record, focus on low drawdown, an ecosystem to retain copiers.
- **Deliverable:** an active lead account.

---

### Go/no-go verdict (2026-06-03)

Honest campaign: 12 coins x 3 years, 1h, net of costs (`research/edge_campaign.py`).
**Result: the v1 strategy (reversion at range edges) has NO edge -> PIVOT.**
- Every config loses (PF 0.72-0.78); all 12 symbols negative.
- **Inverted** calibration (higher score => worse winrate) => a misspecified score.
- Exits: stop 66% vs TP 10% => the "enter at the edge / exit at the opposite one"
  thesis does not hold.
- The earlier 1.89 Sharpe (BTC, 120d) was sample luck (the one favorable window).
- **15m confirms it:** the same campaign on 15m = even worse (PF 0.71-0.76; more
  frequency => more costs). The timeframe is NOT the problem; the SIGNAL is.
- The INFRA (data, backtest, risk, live engine) is solid and reusable; the problem is
  the SIGNAL.
- **Pivot identified (momentum/breakout probe):** reversion loses (PF 0.76) but
  MOMENTUM has the right structure: monotonic calibration (the stronger the breakout,
  the higher the winrate) and the subset of **strong breakouts (>= 1 ATR) is
  POSITIVE** net of costs (PF 1.07, +0.125%/trade, 3092 trades). Verdict: **PIVOT to
  momentum/breakout**, do not discard.
- **OOS validation (breakout_oos.py): edge CONFIRMED out of sample, but THIN.** The
  "stronger breakout -> better" relationship stays monotonic on unseen test data
  (test PF 0.92 -> 1.18). Anchored split TEST: PF 1.01 (breakeven+). Walk-forward OOS
  POOL: PF 1.18, +0.308%/trade, 1505 trades (3/4 folds positive). A real but marginal
  edge: it lives or dies on EXECUTION (maker entries). Project decision:
  **PIVOT = GO**.
- **Robustness + recency:** the edge is broad (9/12 coins) and better in the `range`
  regime; the **`range` + breakout >= 2 ATR** filter **repairs the recent period** (the
  only one with 2025Q4-> positive: PF 1.17). Candidate strategy defined. Caveat: low
  frequency (~323 trades/3y) => noise.
- **Full documentation of the pivot in `docs/FINDINGS.md`** (findings,
  considerations, backlog).
- Prioritized backlog: maker execution (largest impact), confirm the candidate OOS,
  TP/trailing, grow the sample (multi-TF/instruments), portfolio sizing, live forward
  test.
- Reports: `data/reports/{edge_campaign_1h,edge_campaign_15m,momentum_probe,breakout_oos,breakout_robustness,breakout_recency}.md`.

---

## Testing phase - rescuing the BTC/Sentinel project (multi-session)

Context: the review of an earlier local research project (BTC/Sentinel, see
`docs/BTC_SALVAGE.md`) independently confirms Oscilion's pivot: reversion loses,
momentum/trend/breakout win OOS. It contributes data (5 years of 1m BTC + 14 alts),
5 directional strategies and lessons learned. **But its backtests came from an
optimistic harness** => everything is re-validated with Oscilion's honest engine.
Plan per session (each one delivers evidence or kills a hypothesis):

| Session | Goal | Deliverable | Hypothesis |
|---|---|---|---|
| **R0** (done) | Thorough review + plan | `BTC_SALVAGE.md` + this roadmap | - |
| **R1** (done) | Causal 1h -> 2h/4h resample; **honest engine with a pessimistic 15m exit** (`engine_strat.py`); BTC 1m ingested; 15m ~ 1m verified | engine + data | - |
| **R2** (done) | Ported MOMENTUM_PULLBACK and EMA_TREND_STACK; honest **per-coin** validation (default + OOS sweep + walk-forward) + taker/maker check | `VALIDATION_R1_R2.md` | H1 confirmed, H3 (maker is small), H4 confirmed |
| **R3** (done) | Ported **ORB_BREAKOUT** and **BREAK_RETEST** (freshness gate included); validated per coin. **ORB rescues alts** (median +0.029; genuine on LINK/DOT/TRX). break_retest fails except on TRX. VWAP_ANCHOR pending (optional). | `STRATEGY_MAP.md` | H1 confirmed, H2 (gate included) |
| **R4** | **Maker execution**: model limit fills (no-fill / adverse selection) and re-validate the survivors | taker vs maker comparison | H3 |
| **R5** | **Exits**: grid per strategy (fixed TP vs trailing vs hold-to-T2); **regime** and **session** as filters | best exit per tactic | H5, H7, H8 |
| **R6** | **Portfolio**: combine weakly correlated survivors; forward calibration; **live forward test (dry-run)** building a track record | multi-coin signal + monitor | H6 |

Gate for a strategy to "survive": OOS >= 0.70 vs baseline, positive expectancy net
of costs, monotonic calibration, stable in walk-forward. Whatever does not pass is
archived with evidence (not forced). Hypotheses H1-H8 detailed in
`docs/BTC_SALVAGE.md` section 6.

### Building pilot v1 (direction confirmed) - see `docs/PROJECT_STATE.md`
- Done - **Step 1, refactor**: strategies as first-class citizens
  (`oscilion/strategies/`), coin -> strategy map (`assignment.py`), `context.py`
  shared by backtest/live, honest engine re-pointed. Cleanup of the dead
  reversion-live code.
- Done - **Phase A, forward validation**: `live/forward.py` (backtest vs forward per
  coin x strategy -> `forward_results` table), `live/monitor.py` (dry-run: ENTER/EXIT
  alerts + virtual trades with R), orchestrator re-pointed, API `/forward` `/trades`
  `/state`, CLI `python -m oscilion.live.forward`. Standing directive: concise logs in
  the DB, queryable from the frontend.
- Done - **Phase B, portfolio v1** (`research/phase_b.py`, `data/reports/phase_b.md`):
  done with anti-overfit discipline. B1: per-coin tuning overfits -> **fixed baseline
  tp_r=4** (holds OOS on all 6). B2: **equal weight** (edge weighting overfits). B3:
  L = 2%/stop, **no multiplier**. B4: correlation (TRX diversifies). B5: **max 3
  concurrent, 2 per cluster**. B6: OOS portfolio **Sharpe 1.89, return +207%, MaxDD
  -26%** (backtest). Config in `oscilion/strategies/tuned.py` (in use). Future work:
  re-tune with more forward data, dynamic weights, maker fees.
- Done - **Frontend v1** (React + Vite + TS): Overview / Live signals / Forward
  validation views; served by the API; ntfy.sh (private topic).
- Done - **Deploy v1 on an Oracle VM** (2026-06-03): dry-run 24/7, isolated python3.11
  venv, seeded data, dashboard at http://<VM_IP>:8787, one-command
  `bash /opt/oscilion/deploy.sh`. See `docs/DEPLOY.md`. **NOW: daily watch of the
  forward test.**
- Pending - Tune with real forward data, more strategies/coins (SOL/ETH/AVAX, VWAP),
  paper/live.

### Status by phase (as recorded at the time)
- Done - Phase 0: vision and architecture defined (this set of docs).
- Done - Phase 1: system base: `oscilion/` package, config, append-only persistence
  (SQLite WAL), resilient orchestrator, circuit breaker, notify, minimal API and
  deployment (systemd + `deploy.sh`/`setup_vm.sh`). Verified.
- Done - Phase 2: data: `data/{fetch,store,universe,pipeline}.py`, multi-TF OHLCV +
  funding (ccxt/Binance), **no look-ahead** (drops the forming candle), parquet + DB
  (`ohlcv_status`), gap/dupe detection, quality report, CLI `python -m oscilion.data`
  and the `/data` endpoint. Verified against Binance.
- Done - Phase 3: analysis engine: `features/{indicators,reversion,ranges,regime}.py`
  (ATR/BB/Keltner/VWAP/Donchian/ADX/RSI, Hurst/OU/VR/ADF, horizontal range + diagonal
  channel, range|trend|chaos classifier), `scoring/conviction.py` (0-100),
  `risk/{stops,sizing,allocation}.py` (anti-sweep, L = 2%/stop, Kelly + corr) and
  `analysis.py` (ranking + CLI `python -m oscilion.analysis`). Verified: exact risk
  invariant, and the classifier labels a synthetic OU series as `range`.
- Done - Phase 4: honest backtest: `backtest/{costs,metrics,engine,report}.py`,
  event-driven walk-forward WITHOUT look-ahead (decide at the close of i, fill at the
  open of i+1; conservative intrabar, stop first), real costs (maker/taker fees,
  slippage, 8h funding), metrics (Sharpe, MaxDD, winrate, PF, MAE/MFE, calibration)
  and a go/no-go report. CLI `python -m oscilion.backtest`. Reuses the SAME signal as
  live (`candidate_from_df`). Initial verdict (naive logic, ~120d 1h): **NO-GO** (no
  turn confirmation yet; trending market). Multi-year validation + phase 5's turn
  confirmation still pending.
- Done - Phase 5: live engine: `signals/{entry,exit,maker_taker,state_machine,live}.py`
  + `scoring/calibration.py`. Per-coin state machine (WAITING -> APPROACHING ->
  IN_TRADE) with **turn confirmation**, exit management (stop/tp/break/trailing/
  partial), maker vs taker, forward calibration and ENTER / TAKE PROFIT / EXIT
  alerts. Integrated into the orchestrator (live monitor, no trading); API `/state`
  and `/calibration`. Turn confirmation is also optional in the backtest
  (`--confirm`).
  **Phase 5 finding (1h, ~120d):** turn confirmation flips the edge. WITHOUT: winrate
  28%, PF 0.87, Sharpe -0.47, return -41%. WITH: winrate 40%, PF 1.22, Sharpe 1.89,
  return +47%. Formal verdict still NO-GO (PF 1.22 < 1.3) and a short sample:
  **promising, not confirmed**. Multi-year validation pending. (It was later run: see
  the 2026-06-03 verdict above; the 120-day result did not survive 3 years.)
- Phase 6: frontend. Built afterwards as part of pilot v1 (see above).

### Final status (2026-08-03): project closed

The pilot ran in dry-run on the VM from 2026-06-08 to 2026-08-02 and was evaluated
against its own go/no-go criteria in `docs/AUDIT_2026-08-03.md`: 110 closed forward
trades, -64.2R, 14.5% winrate against a 31.4% breakeven. Four strategies were
discarded on decisive evidence; the fifth (`break_retest`) was inconclusive and
discarded for lack of a reliable validation method. The VM service was stopped and the
DB kept as evidence. Verdict: **there is no edge; the project is closed.** The phase 5 live
modules listed above (`signals/state_machine.py`, `exit.py`, `maker_taker.py`,
`live.py`, `scoring/calibration.py`) were superseded by the pilot's
`oscilion/live/` layer and are no longer in the repository; see ARCHITECTURE
section 8.
