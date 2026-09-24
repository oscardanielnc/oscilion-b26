# Oscilion project status - v1.0 (CLOSED: there is no edge)

**Updated:** 2026-08-03 (final closing audit). Governing document:
**`AUDIT_2026-08-03.md`**. Everything below (v0.9 and earlier) is **historical**.

---

## v1.0 (2026-08-03) - GO/NO-GO VERDICT: **THERE IS NO EDGE. PROJECT CLOSED.**

> **One line:** the full forward test (110 trades, 08-Jun -> 02-Aug, dry-run) returned
> **-64.2R with a 14.5% win rate** in a **sideways** market (BTC +0.4% over 8 weeks), that
> is, in the regime the thesis claims to exploit; and the backtest -> forward correlation
> per combo turned out **zero/negative** (Spearman -0.18), so what got refuted is not the
> five strategies but **the method that selected them**.

**Result:**

| Metric | Value |
|---|---|
| Cumulative R | -64.2R |
| Win rate | 14.5% (breakeven 31.4%) |
| Peak equity / MaxDD | +0.3R / -64.4R (monotonically falling) |
| Worst streak | 18 losers in a row |
| P(this \| true expR = 0) | < 1e-4 (Monte Carlo, 20k sims) |

**Strategies - all discarded:**

| Strategy | n | expR | p(expR>=0.10) | Verdict |
|---|---:|---:|---:|---|
| `ema_trend_stack` | 16 | -1.077 | 1e-26 | discarded (0 winners out of 16) |
| `orb_breakout` | 24 | -0.639 | 5e-5 | discarded (average winner 0.72R: the RR >= 2.5 does not exist) |
| `vwap_anchor` | 49 | -0.498 | 1e-3 | discarded |
| `momentum_pullback` | 2 | -1.236 | 2e-3 | discarded |
| `break_retest` | 19 | -0.248 | 0.23 | inconclusive -> discarded for lack of a reliable method |

**Central finding:** of 22 combos with a positive expR in OOS-2026, only **2 (9%)** were
positive in the forward test, both with n <= 4; the 22 together **-65.1R over 102 trades**.
The double-OOS + anti-beta + purged-WF + adaptive-gate pipeline **selects noise**. Any
future strategy validated with this method will repeat the result.

**Also:** with 0.54 trades/week per combo and sd 1.25R, detecting a +0.30R edge would take
**4.9 years per combo** -> the v0.9 rule ("wait for ~100 capital trades") was
mathematically unworkable at that granularity. Costs were honest and minor (-7.5R of the
-64R, 12%).

**Actions taken:** the `oscilion` and `oscilion-api` services were **stopped and disabled**
on the VM on 2026-08-03; the DB is kept as evidence; **real capital was never traded**.

**If it is ever resumed:** the prerequisite is NOT a new strategy, it is **redoing the
validation** (family level rather than combo level; fewer free parameters; a much larger
trade horizon per decision unit).

The honesty invariant in `VISION.md` ("the backtest may say *there is no edge*: that is
accepted") holds here in its strongest form: **the forward test said it, and it is
accepted.**

---

## v0.9 (2026-07-02) - data integrity, gate on the real book, and FREEZE

> **One line:** with 44 closed trades (08-Jun -> 02-Jul) the profitability verdict is
> **statistically INCONCLUSIVE** (capital: 34 trades, mean -0.42R, 95% CI [-0.94, +0.11])
> and the sample under v0.8 rules is only 3 trades -> 2 integrity bugs are fixed, the
> **engine is FROZEN** and sample is accumulated without touching anything until ~100
> capital trades or mid-September 2026, whichever comes first.

**Sample audit (VM data as of 02-Jul):**

| Era | Capital trades | Total R | Mean R | Win% |
|---|---|---|---|---|
| pre-v0.7 (08-22 Jun) | 20 | -14.4R | -0.72 | 15% |
| v0.7 (22-29 Jun) | 11 | -2.4R | -0.22 | 18% |
| v0.8 (29 Jun ->) | 3 | +2.7R* | - | - |

\* Careful: the +4.78R PAXG trade attributed to v0.8 turned out to be a trade OPENED on
23-Jun (v0.7), uncovered by bug #1. The mean improves era by era, but nothing is
conclusive: detecting a +0.3R edge with sd ~ 1.55R takes **~100 trades under frozen rules**.

**Fixes (this version):**

1. **`trades.ts` = the real OPEN time** (`monitor._close` now passes `ts=pos["entry_ts"]`;
   before, it fell back to the default = close time -> every time/era analysis was
   corrupted). The 44 historical rows keep the defect (ts ~ close); the era analysis of old
   rows must use `exit_ts` with caution.
2. **The gate decides with the REAL BOOK** (`db.real_forward_stats`: `trades` table,
   capital + observe, since `config.gate_real_fw_from_ms` = start of v0.8). Before,
   kill-switch and graduation read the `forward` scope = an engine simulation with the
   current rules, which diverged from the desk (XAU momentum: **+1.35R simulated vs -2.47R
   real**) because it simulates entries the monitor never took (portfolio vetoes,
   downtime) and misses the ones it did take. The `forward` scope stays as a dashboard
   diagnostic; it does not decide capital.

**Healthiest candidate so far** (the only one consistent backtest -> OOS-2026 ->
forward): HBAR break_retest (+0.24 bt n=46 / +0.30 oos26 / +0.75 fw n=6). None meets the
graduation rule yet (real n >= 20).

**FREEZE:** from this deploy on, the engine, gate, portfolio and thresholds are NOT
touched. Only watching (dashboard/events) and letting the gate self-correct
(kill/graduation are automatic). Review: **~100 capital trades or 2026-09-15**. Open risk
#1 (sizing 2% -> ~0.5% before real capital) still stands and does NOT require touching the
engine now.

Tests: **41/41**.

---

## v0.8 (2026-06-29) - audit of the live forward (historical)

> **One line:** the first week live gave a capital book of **-16.85R / 16% win**.
> Dissection: (a) vwap_anchor (long-only) bled -11R buying bull traps on falling alts,
> WITHOUT a regime guard; (b) tight stops (gold/TRX) were cost-toxic; (c) the gate **never
> looked at the real forward** -> observe (+1.77R) beat capital. Five fixes, all measured
> with the honest engine + tests (37/37).

**What changed (commits `d38671a`, `75a123e`, `e6e0212`):**

1. **Market regime gate** (`features/market_regime.py`, single source for live +
   backtest): do not trade while the benchmark (BTC vs 4h EMA50) runs AGAINST the trade's
   side. Backtest OFF -> ON: **W1-2025 neutral (+0.087 -> +0.088), W2-2026 +0.357 -> +0.632
   (+77%)**; it pays in a hostile regime and does not hurt in a benign one.
   `research/regime_backtest.py`.
2. **Anti-beta exemption**: break_retest and gold (PAXG/XAU per symbol) are EXEMPT; their
   edge is anti-beta (shorts on alts falling independently of BTC); a beta filter breaks
   them (FLOW lost 3 winning shorts worth +4.42R). `portfolio.regime_exempt()`.
3. **Cost filter** (`CostModel.round_trip_cost_r`, `max_cost_r=0.12`): rejects entries with
   a round-trip cost > 12% of R (tight stops => big notional => fees eat the R; XAU -0.24R,
   TRX -0.14R per trade). Takes gold out of the book.
4. **ADAPTIVE forward-aware gate** (`guards.gate_decision`): closes the loop with reality.
   - **KILL-SWITCH**: a capital combo whose real forward bleeds (n >= 15, exp_R <= -0.10)
     -> observe.
   - **GRADUATION**: an observe combo whose forward confirms (n >= 20, exp_R >= +0.10) ->
     capital (before, the code promised this and did NOT do it).
   - **Recency-aware ROBUST**: the RECENT OOS window (2026, n >= 20) must not be decaying.
     It does NOT require both windows positive, which would kill emerging alpha
     (RUNE/NEO: -0.23 in 2025 but +1.07 in 2026). forward.refresh persists the
     `oos_a`/`oos_b` scopes.
5. **Hygiene**: `_refresh_funding` on a cadence (~8h; before, the parquet froze and trades
   closed with fund=0) + the `fees` column populated in `log_trade`.

**EFFECTIVE portfolio after the gate (preview with real stats): 17 -> 8 with capital**, 15
observe.

| Cluster | Effective capital | Note |
|---|---|---|
| `trx` | TRX x {ema, orb, break_retest} | vwap demoted to observe |
| `altlong` | XRP orb | LINK/DOGE orb to observe (n<30 after the regime filter) |
| `altbreak` | RUNE, NEO, FLOW, HBAR break_retest | anti-beta alpha, regime-exempt, +1.07/+1.02 in 2026 |
| `gold` | - | XAU/PAXG to observe (n<30 / cost-toxic) |

**The whole vwap_anchor family -> observe** (it bled live). It **re-graduates on its own**
if its forward with the regime filter confirms (n >= 20, exp_R >= +0.10), exactly "prove it
before recapitalizing". The system now self-corrects without intervention.

**Open risk #1 (unchanged):** 2%/trade sizing => backtest MaxDD ~-60%. Deferred: in dry-run
everything is measured in R. Lower it to ~0.5% (half Kelly) BEFORE real capital.

---

## v0.7 (2026-06-22) - portfolio v2 (historical)

**Updated:** 2026-06-22 (hard audit + portfolio rebuild by OOS edge + anti-beta + universe
expansion). Also read `AUDIT_2026-06-22.md` (the full audit and the method),
`FORWARD_REVIEW.md`, `STRATEGY_MAP.md`.

> **One-line summary (2026-06-22):** the audit refuted the "overfit" fear (purged WF leaves
> the combos positive) and revealed that the problem was the **gate** (it read an
> in-sample backtest inflated 2-3x and picked losers). Fixed: OOS gate + a capital rule by
> **double OOS regime + anti-beta**. Portfolio rebuilt to **17 capital combos + 6
> observe** (including gold and alts with real alpha on the short side). **Deployed and
> verified live on 2026-06-22.** Open risk #1: 2%/trade sizing gives a backtest MaxDD of
> ~-60% -> lower R before real capital (see section 7).

---

## 1. Direction (confirmed by the project owner)

**Oscilion = a multi-coin observer that assigns EACH coin the strategy validated for it,
lets winners run, and only trades where there is a proven edge.** Conviction over quantity.

**Portfolio v2 (2026-06-22): 17 with capital + 6 observe, 17 coins.**
Capital rule: exp_R >= +0.10 in TWO OOS regimes (holdout >2025 **AND** 2026) with n >= 30,
15m exit, real costs, **and** passing the anti-beta check (it pays on the short side or
with a flat asset, not by riding a rally). FIXED config per strategy.

| Cluster | Combos with capital | Edge (OOS/2026) |
|---|---|---|
| `trx` | TRX x {vwap, ema, orb, break_retest} | +0.13..+0.34 / +0.45..+0.99 |
| `altlong` | LINK orb, XRP orb, DOGE orb, BNB vwap, AVAX vwap, TIA vwap, ATOM vwap | +0.10..+0.37 |
| `altbreak` | RUNE, NEO, FLOW, HBAR - break_retest (alpha on the SHORT side on falling alts) | +0.13..+0.34 / +0.15..+1.07 |
| `gold` | PAXG break_retest, XAU momentum (uncorrelated with crypto) | +0.15..+0.47 |

**Observe (no capital):** BTC ema, BTC orb, BNB ema, ETH vwap, DOT orb, **PAXG ema**
(demoted: it was gold's +41% beta). Pruned: BTC/DOGE/XRP vwap (negative in both regimes).

**"Capital" is always conditioned on the dynamic gate** (see section 3), now measured on
the OOS window `[2025-01, inception)` (not in-sample) with `exp_R > +0.05`. Portfolio
limits: **max 4 concurrent (raised from 3 with `concurrency_sweep.py`), max 2 per
cluster.**

## 2. Architecture (at the time)

```
oscilion/
|-- strategies/          single source of the signal
|   |-- library.py       5 pure strategies + tp_barrier (runner = tp None)
|   |-- context.py       multi-TF build_ctx (backtest AND live), no look-ahead
|   |-- assignment.py    PORTFOLIO: coin -> strategy(ies) + params + observe_only
|   |-- portfolio.py     weights/clusters/limits (tuned.py from phase B)
|   `-- tuned.py         GENERATED in phase B: equal weight, maxc=3, cluster=2
|-- live/                PHASE A (validation with real data)
|   |-- monitor.py       dry-run: signals -> virtual trades; ALL the guards (section 3)
|   |-- guards.py        PURE guards: gate, vetoes, daily brake, stale, stop floor
|   |-- forward.py       backtest vs forward per series -> forward_results (DB)
|   |-- signals.py       curated view for the frontend
|   `-- export.py        daily md/json report (capital vs observe separated)
|-- backtest/            engine_strat (honest engine), costs (shared with live), resample
|-- data/                fetch (ccxt + explicit timeout), store, universe, pipeline
|-- persistence/         db, models - **schema v6** (trades: observe, exit_reason, cost_audit)
|-- api/app.py           /signals /trades /forward /alerts /export /portfolio /events ...
|-- orchestrator.py      resilient 24/7 loop + slow-tick warning + daily DB backup
`-- circuit_breaker, notify, logging_setup
```

**Tests: 23 (pytest)** at the time: smoke (imports, risk, causal resampling,
production/research separation, single universe) + guards (gate, vetoes, brake, stale, tp
runner, stop floor).

## 3. Process guards (evaluation order on open) - ALL enforced in the monitor

They were born from the first forward cycle (-4.07R, of which -3.2R came from unvalidated
combos; see `FORWARD_REVIEW.md`). Every block leaves an event in the DB (visible in
/alerts and the export).

1. **Stale signal** (`max_signal_age_min=30`): an old signal candle (downtime / failed
   refresh) -> do not enter at a stale price.
2. **Stop floor** (`min_stop_pct=0.2%`): stop -> 0 blows up the notional. Identical in the
   engine.
3. **Validation gate** (`gate_min_n=30`, `gate_min_exp_r=+0.05`): capital only if the
   LOCAL backtest backs it; otherwise -> demoted to **observe** (no capital, `observe=1`,
   out of the PnL, keeps adding stats). **2026-06-22:** the gate backtest is measured on
   the **OOS window `[2025-01, inception)`** (`gate_backtest_from_ms`), not in-sample full
   history (which inflated exp_R 2-3x and picked losers; see `AUDIT_2026-06-22.md`).
4. **Symbol veto**: max 1 position WITH capital per symbol (any direction).
5. **Portfolio limits (phase B)**: max 3 capital positions, max 2 per cluster, the scheme
   the portfolio was validated with (before, it was NOT applied live).
6. **Daily brake** (`max_daily_loss=6%`): closed PnL for the (UTC) day <= -6% of capital
   -> no new capital entries until 00:00 UTC + a CRITICAL ntfy alert (1 per day).

**Cost audit**: every close persists `cost_audit` (R = r_gross + r_slip_exit + r_fee_entry
+ r_fee_exit + r_funding) -> answers with data whether stops realize worse than -1R
because of the model or something else. Finding: monitor and backtest share
`costs.realized`; the observed -1.04/-1.13R IS already modeled.

## 4. How to run / deploy

```powershell
python -m oscilion                  # 24/7 orchestrator
python -m oscilion.api              # API + frontend
python -m oscilion.live.forward     # backtest vs forward review
python -m pytest tests/ -q          # tests
```
Deploy: `git push` -> on the VM `bash /opt/oscilion/deploy.sh`. The DB migrates to schema
v6 by itself (idempotent migrations on startup). Dashboard http://<VM_IP>:8787.

## 5. Done
- Pilot v1 + frontend + Oracle VM (dry-run) + ntfy + daily export.
- 2026-06-08/10: first forward cycle closed and reviewed (FORWARD_REVIEW.md).
- 2026-06-10 (`10c1c8e`): validation gate + enforced observe + symbol veto + stale signal
  + tp runner None + stop floor + cost_audit (schema v6).
- 2026-06-10 (`033e52c`): phase B portfolio limits live + -6% daily brake + explicit ccxt
  timeout + slow-tick warning + state only persisted after a successful step.
- **2026-06-12: deployment CONFIRMED live** (cost_audit populated, stops at exactly
  -1.04R, errors: []).
- **2026-06-22: HARD AUDIT + PORTFOLIO v2 (deployed and verified).** See
  `AUDIT_2026-06-22.md`.
  - Cumulative forward of 26 trades / -10.6R analyzed: it was NOT overfit (purged WF,
    `research/purged_wf.py`, leaves the combos positive; 2026-YTD healthy); it was a tiny
    sample + a hostile fortnight + an **inflated gate** (in-sample full history, +1.23 vs
    +0.39 real OOS) that picked losers. (Later refuted by the final audit.)
  - **Gate fixed** to the OOS window + `exp_R > +0.05` (commit `fa1f653`).
  - **Portfolio rebuilt** by double OOS regime + **anti-beta** (`validate_alts.py`; lesson
    from `tvindicators`: long-only gold = beta). 17 capital + 6 observe; expanded to alts
    (RUNE/NEO/FLOW/HBAR break_retest, alpha on the SHORT side) and gold (commit `1bb1afc`,
    + concurrency). 15m history for 8 new coins seeded on the VM.
  - **`max_concurrent` 3 -> 4** by evidence (`research/concurrency_sweep.py`: it dominates
    3 on return, Sharpe and MaxDD).

## 6. Live status + what to expect (at the time)

**Deployed 2026-06-22:** services `active`, `forward refresh: 23 series, 0 dark`, no errors.
The gate reads OOS (PAXG bret +0.51, TRX vwap +0.32...). It is NORMAL to see OBSERVE alerts
besides ENTER, and some "demoted to observe" / "stale signal" (guards working).

**Standing criterion:** accumulate gated forward trades from portfolio v2 (now with 17
combos and 4 concurrent => much faster than the previous ~0.5 trades/day) and watch that the
forward confirms the OOS. Do NOT loosen the gate or the anti-beta check. Expand only with
combos that pass `universe_scan.py --tf 15m` + `validate_alts.py` (15m + double OOS +
anti-beta).

## 7. Open risk #1 - SIZING before real capital

`concurrency_sweep.py` showed a **backtest MaxDD of ~-60% at `risk_per_trade=2%`** (the -6%
daily brake is not in that sim and would help, but the tail is high). In dry-run it does not
affect the track record (everything is measured in R). **Before moving to paper/live, R per
trade must be lowered** (half Kelly, `tvindicators`-style R=0.5% -> p95 MaxDD ~-14%) and/or
risk-adjusted edge weights. The owner's decision; it is the risk invariant, not to be
touched blindly. Calibrate with a dedicated portfolio sim.

**Backlog:** DB retention + VACUUM; an explicit graduation/demotion rule for observe; once
there are real fills, compare fill vs `cost_audit`; delete research/legacy code; GitHub CI.

> Key docs: `AUDIT_2026-06-22.md`, `FORWARD_REVIEW.md`, `STRATEGY_MAP.md`, `DEPLOY.md`.
