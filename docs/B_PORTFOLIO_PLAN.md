# Phase B - Portfolio and tuning (test plan)

> Goal: **maximum profit with minimum risk** over the validated core (BTC/BNB/TRX with
> EMA_STACK; LINK/DOT/TRX with ORB). Everything is validated with the honest engine +
> forward; nothing is fixed without evidence. Primary metric: expectancy in R and, at the
> portfolio level, the real Sharpe/MaxDD of a single account.

---

## Questions to answer (ALL of them, nothing left in the air)

### B1 - Best parameters per coin
Each coin may have its own optimum. Sweep the params of its strategy per coin
(train -> OOS -> walk-forward) and fix the best **robust** ones (not the train peak).
- EMA_STACK: `atr_mult_sl`, `tp_r`, `fresh_gate`, `session_filter`, `rsi_filter`.
- ORB: `range_max_pct`, `tp_r`, `fresh_gate`, `long_only`, `session_filter`, `sl_atr_buf`.
- Harness: `research/strat_validation.py` (already does default + OOS sweep +
  walk-forward per coin).
- Criterion to "stay": positive full + OOS + WF, coherent calibration/forward.

### B2 - Capital per coin (weights)
How much capital goes to each series. Proposal to validate: `weight ~ measured_edge(exp_R)
x (1/vol) x correlation_haircut`, with **fractional Kelly** as the cap.
- Deliverable: a table of weights per series, justified by a portfolio backtest.

### B3 - Leverage multiplier per coin
On the allocated capital, `L = 2% / stop%` (invariant) already fixes the risk; B decides
whether there is an extra multiplier by conviction/regime and its cap. Validate that it
does not break the -2%/trade.

### B4 - Correlation map (v1 done - `data/reports/correlation_map.md`)
**Finding:** **TRX is a diversifier** (corr ~0.4 full, ~0.1 recent with everything).
BTC/BNB/LINK/DOT are a **correlated cluster** (~0.68-0.78; LINK-DOT 0.78).
- Sizing rule: **treat the correlated cluster as ~one single bet**; TRX counts separately.
  Do not open full size on BTC+BNB+LINK+DOT at the same time.
- Pending: re-run periodically (correlation changes with the regime).

### B5 - Hard limits
`MAX_CONCURRENT` (3?), `MAX_TOTAL_EXPOSURE` (100%?), max per correlated cluster. Validate
the worst case (every coin in the cluster hits its stop on the same day ~ -2% x
n_effective).

### B6 - PORTFOLIO simulation (single account)
Combine every series into ONE account (finite capital, limits, correlation) and measure
the **REAL Sharpe/MaxDD/return**, the risk that is actually lived. Today the backtests are
per independent series; the joint view is missing.

---

## Suggested order
B1 (best params) -> B4/B5 (correlation + limits) -> B2/B3 (weights + leverage) -> B6
(portfolio) -> forward of the full portfolio. Iterate until the profit/risk balance is
reached.

## B v1 results (2026-06-03) - `data/reports/phase_b.md`

Run honestly (selection on train, genuine OOS = 2025->):

- **B1 - params per coin:** **per-coin tuning OVERFITS** on small samples (BTC ema train
  +0.80 -> OOS -0.00; TRX ema +0.77 -> +0.05). **Decision: do NOT tune; use the fixed
  `tp_r=4` baseline**, which holds OOS on all 6 (BTC +0.13, BNB +0.41, TRX +0.14/+0.34,
  LINK +0.37, DOT +0.11). Anti-overfit discipline.
- **B2 - weights:** equal weight beats in-sample edge weighting (which overfits).
  **v1 = equal weight.**
- **B3 - leverage:** keeps `L = 2%/stop` (invariant); **no extra multiplier** in v1
  (conviction showed no edge -> do not add risk).
- **B4 - correlation:** TRX diversifies (~0.1 recent); {BTC,BNB,LINK,DOT} cluster (~0.7).
- **B5 - limits:** **max 3 concurrent, max 2 per cluster** (concentration control).
- **B6 - portfolio (single account, OOS):** best robust scheme = **equal + maxc3 + clu2**
  -> **OOS Sharpe 1.89, return +207%, MaxDD -26%** (533 trades). "No limits" gave a
  Sharpe of 1.98 but with uncontrolled concentration -> discarded for risk.

**Honesty:** the returns come from a compounded backtest and must be **confirmed in the
FORWARD test (phase A) on the VM** before being believed; the sober number is the **~26%
MaxDD** (the pilot's real risk). The chosen config is persisted in
`oscilion/strategies/tuned.py` (generated, in use). (It was not confirmed: see
`docs/AUDIT_2026-08-03.md`.)

**Pending B (future, with more forward data):** re-tune params once there is more
sample, validated dynamic weights, re-run correlation periodically, simulate with maker
fees.

## Scaffold status (at the time)
`oscilion/strategies/portfolio.py` had a provisional `equal_weights()` + limits + TODOs,
and `assignment.py` had `weight=None` per series for B to fill in. Both placeholders
were later removed as unused: weights, clusters and limits live in
`oscilion/strategies/tuned.py`. The engine (`engine_strat`) and the harness
(`strat_validation`) serve all of these tests.
