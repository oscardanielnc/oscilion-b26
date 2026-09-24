# Oscilion - Edge validation findings

> Honest record of the validation campaign (2026-06-03). It summarizes what was tested,
> what the data said, what to consider and what to test next.
> Raw reports: `data/reports/*.md` (gitignored, reproducible).

> Note added at closing: the momentum/breakout pivot and the directional strategies
> described here were later deployed in dry-run and failed the forward test. See
> `docs/AUDIT_2026-08-03.md`.

---

## 0. TL;DR

- **The original thesis (reversion at range edges) has NO edge.** 12 coins x 3 years, 1h
  and 15m, net of costs: every config loses (PF 0.72-0.78) and the **calibration is
  inverted** (higher score => worse). Buried with evidence.
- **Pivot to momentum/breakout: a real edge.** The *breakout* works where the *bounce*
  fails, exactly the risk that the "honest verdict" section of VISION.md flagged as
  decisive.
- **Validated OOS** (threshold chosen only on train): the "stronger breakout => better"
  relationship stays **monotonic on unseen data**; walk-forward OOS POOL PF 1.18.
- **Candidate strategy: strong range breakout.** `range` + breakout >= 2 ATR +
  confirmation -> PF 1.37, +0.46%/trade, 38% winrate, and **positive even in the recent
  period** (the only filter that repairs 2025Q4->).
- **Caveats:** a **thin, low-frequency** edge (~323 trades / 3 years / 12 coins). It lives
  or dies on **execution (maker)**. Moderate-positive confidence, not high.

**Project decision: PIVOT = GO** (develop momentum/breakout). Infra, risk and the live
engine are reused as is; only the signal changes.

---

## 1. Timeline and evidence

| Step | Question | Result |
|---|---|---|
| 1h campaign | Does reversion have an edge on 12 coins x 3 years? | No: PF 0.76; **inverted calibration**; stops 66% vs TP 10% |
| 15m campaign | Does the timeframe change it? | No: worse (PF 0.72; more frequency => more costs) |
| Momentum probe | Is the edge in the opposite direction? | Yes: momentum has **monotonic** calibration; breakouts >= 1 ATR positive |
| OOS validation | Real or data snooping? | Real: monotonic on unseen test; walk-forward OOS POOL PF 1.18 |
| Robustness | Stable or concentrated? | Broad (9/12 coins), better in `range` than `trend`; red flag: last 3 quarters negative without a filter |
| Recency | Does `range` + >= 2 ATR repair recency? | **Yes**: the only filter with a positive recent period (PF 1.17) |

### Key tables

**Reversion vs momentum (1h, 12 coins x 3 years, per trade, net of costs):**

| Strategy | N | Winrate | PF | Exp/trade | Calibration |
|---|--:|--:|--:|--:|---|
| Reversion + turn confirmation | 5747 | 30.3% | 0.76 | -0.256% | inverted |
| Momentum (all breakouts) | 7857 | 17.7% | 0.94 | -0.073% | monotonic |
| Momentum strong breakouts >= 1 ATR | 3092 | 28.9% | 1.07 | +0.125% | monotonic |

**OOS (threshold chosen only on train):** a grid with a monotonic relationship on TEST (PF
0.92 -> 1.18 as the threshold rises). Anchored split TEST: PF 1.01 (breakeven+).
Walk-forward OOS POOL: PF 1.18, +0.308%/trade.

**Stability per threshold (3 years):** PF rises up to ~2.0-2.5 ATR (PF 1.15-1.20), then
the sample collapses (2.5 ATR = 246 trades; 3.0 = 65, noise).

**Recency - `range` + >= 2 ATR (the candidate):**

| Scope | N | Winrate | PF | Exp/trade |
|---|--:|--:|--:|--:|
| ALL (3 years) | 323 | 38.4% | 1.37 | +0.456% |
| earlier (->2025Q3) | 246 | 38.6% | 1.44 | +0.512% |
| **RECENT (2025Q4->)** | 77 | 37.7% | **1.17** | **+0.277%** |

Loosening either of the two filters (>= 1.5 ATR, or all regimes) => the recent period
turns **negative**. It is the combination that repairs it.

---

## 2. Candidate strategy (current spec)

```
Signal:    continuation range breakout, NOT reversion.
Setup:     regime = range (price had been oscillating in a band) AND the close
           breaks an edge by >= 2 * ATR.
Side:      bullish breakout -> long ; bearish breakout -> short.
Confirm:   candle in the direction + momentum (RSI) following.
Stop:      back inside the range (broken edge -/+ ATR buffer), anti-fakeout.
TP:        measured move = projection of the range width.
Risk:      2% of equity per trade; L = 2% / stop% (invariant intact).
Frequency: LOW (~108 trades/year across 12 coins). Quality over quantity.
```

Implementation: `oscilion/analysis.py::breakout_candidate`, the `engine` with
`BTParams(strategy="momentum", min_breakout_atr=2.0, allow_regimes=("range",))`.

---

## 3. Considerations (read before continuing)

**Methodological**
- **Pooled return/Sharpe/MaxDD metrics are NOT reliable** (they merge 12 independent
  backtests, each sized at 2% of ITS equity -> the fictitious account goes to ruin; the
  -100%/-98% gives it away). ALWAYS use the **per-trade** ones: winrate, PF, expectancy
  and calibration.
- The >= 2 ATR threshold was chosen by looking at the data; mitigated with OOS
  (train/test + walk-forward) but **it should be re-confirmed** whenever anything changes
  (costs, TF, universe).
- **No look-ahead** guaranteed: decision at the close of bar i, fill at the open of i+1;
  conservative intrabar (stop before TP).

**Risk / business**
- **Low frequency => small sample => high noise** per quarter. The bottleneck is the
  number of trades. More instruments / multi-TF would give more sample.
- **Thin edge (+0.28 to +0.46%/trade) => costs rule.** The probe used taker + slippage
  (worst case). **Maker** entries could be the difference between tradeable and not.
- **Recency:** repaired by the filter, but 2026Q1 is still negative and the recent buckets
  are small. Watch it in the forward test.
- Breakouts in the `trend` regime lose (they arrive late); that is why the `range` filter
  matters.

**Infra / reproducibility**
- Parallel backtest on Windows: **set `OMP/OPENBLAS/MKL_NUM_THREADS=1` before importing
  numpy** or it hangs from BLAS thread oversubscription (already done in the `research/`
  scripts).
- Reproduce: `python -m oscilion.data sync --days 1095` and then the `research/` scripts
  (see section 5).

---

## 4. Prioritized backlog (what to test)

1. **Maker execution** (largest impact). Model limit entries (at the level / on the
   retest, with no-fill) in the engine and re-validate OOS. A thin edge is won or lost here.
2. **Confirm the candidate OOS** with the full filter (`range` + >= 2 ATR) in a dedicated
   walk-forward (not just the loose threshold).
3. **TP/exits for momentum:** measured move vs trailing (let winners run; momentum has fat
   tails). Today the fixed TP may leave money on the table.
4. **Grow the sample:** multi-TF (4h/1h/15m combined), more liquid instruments, without
   overfitting the threshold per TF.
5. **Portfolio sizing** with the real edge (fractional Kelly over measured expectancy +
   correlation). The per-trade edge is thin: portfolio construction matters.
6. **Rebuild the `score`** for momentum (today it is only breakout strength). Look for
   features that improve the monotonic calibration (volume on the breakout, prior range
   compression, etc.).
7. **Recent regime detection** (adaptive filter): if the market goes choppy/anti-breakout,
   reduce or pause.
8. **Live forward test** (dry-run) of the candidate to build an out-of-sample track record.

---

## 5. Research scripts (`research/`)

| Script | What it does | Report |
|---|---|---|
| `edge_campaign.py --tf {1h,15m}` | reversion vs variants, per symbol/semester/regime/calibration | `edge_campaign_{tf}.md` |
| `momentum_probe.py` | reversion vs momentum + strong breakout filter | `momentum_probe.md` |
| `breakout_oos.py` | OOS validation (anchored split + walk-forward) | `breakout_oos.md` |
| `breakout_robustness.py` | threshold, quarterly recency, regime, vol, symbol | `breakout_robustness.md` |
| `breakout_recency.py` | does the range + >= 2 ATR filter repair recency? | `breakout_recency.md` |

All of them parallelize per symbol (12 cores) with the BLAS thread pin.

---

## R6 - EMA-trend trade horizon (2026-06-04)

> Does shortening the hold (timeout 240h ~ 10d) reduce risk without killing the edge?
> Honest engine, fixed validated entry, only the exit changes. OOS = 2025->.
> Raw report: `data/reports/r6_exit_horizon.md` (reproducible: `research/exit_horizon.py`).

**Frame:** the **real median hold is ~2 days**, not 10; the 10d timeout only bites 6-18%
of trades (the tail). Crypto trades 24/7 -> **no weekend gaps**; funding is already costed.

**OOS evidence (exp_R):**

| Coin | baseline 240h | 120h | 96h | 72h | Reading |
|---|---:|---:|---:|---:|---|
| BTC | **+0.131** | +0.021 | -0.007 | -0.105 | shortening **destroys** the edge (monotonic) |
| BNB | **+0.407** | +0.348 | +0.222 | +0.065 | 120h almost free; < 96h collapses |
| TRX | +0.137 | +0.123 | -0.074 | +0.141 | tolerates 72-120h, ~neutral |

Trailing (1.5/2/3 ATR) and time-stops <= 72h came out negative or worse -> **confirms
lesson #9 (cutting winners hurts)**. The trend edge lives in the runners.

**Decision:** BTC keeps 240h (do not touch). **BNB and TRX -> 120h cap** (`max_hold` 30 4h
bars): ~free in OOS and eliminates 100% of the 10-day zombies (timeout 6-8% -> 0%).

**Collateral bug fixed:** the live monitor did NOT apply the timeout (`_manage` only closed
on stop/tp -> an eternal position). It now closes at market when the horizon expires
(reason `timeout`, TIME_EXIT alert), consistent with the honest engine.

---

## R3b - momentum_pullback + break_retest campaign (2026-06-04)

> Validate the 2 coded-but-not-deployed strategies on the 12 coins, honest engine,
> full + sweep (train -> test) + walk-forward (primary verdict). `research/strat_validation.py`.

**`momentum_pullback` -> REJECT.** 12 coins, only 3 positive in WF and marginal (SOL
+0.056, XRP +0.064, LTC +0.201); median -0.081; default full negative on all 12. Edge ~
noise. Do not deploy.

**`break_retest` -> fails in general, TRX is a candidate.** Median -0.161 (11/12 negative).
**TRX robust in EVERY slice:** full +0.608, test +0.190, sweep +0.391, **WF +1.451 (n=67,
WR 30%)**. Cfg: long_only, retest_half_atr=0.3, tp_r=0 (no TP), trend_filter=False,
vol_max_ratio=1.0.

**Asterisk:** TRX = 1 of 24 combos -> multiple-comparisons risk; TRX also already carries
ema + orb (concentration). Decision: do NOT deploy with capital yet -> **forward-test** TRX
break_retest before giving it weight.

---

## R3c - vwap_anchor validation (2026-06-04)

> Faithful port from Sentinel (VWAP Anchor v2, LONG-only). Entry gate = C1 (price > 1h
> VWAP) and C2 (price > 4h VWAP) and O1 (freshness, 1h EMA9 < EMA21). C3 (4h EMA50)
> optional. SL = k * 1h ATR, TP = tp_r * R. signal_tf = 1h, aux = 4h, max_hold = 120 (5d).
> `research/strat_validation.py vwap_anchor`.

**Verdict: GENERALIZABLE EDGE (the best of the 3 ported).** 12 coins, **6 positive in WF
OOS**, equal-weighted median **+0.069** (positive, vs -0.08/-0.16 for momentum/break_retest).

| Survivor | Verdict | full | TEST | WF OOS (n) |
|---|:--:|---:|---:|---:|
| TRX | PASS | +0.220 | +0.318 | **+0.877** (72) |
| ETH | PASS | +0.023 | +0.111 | **+0.173** (90) |
| AVAX | PASS | +0.171 | +0.104 | **+0.154** (68) |
| BTC | MARGINAL | +0.035 | -0.014 | +0.608 (43) |
| XRP | MARGINAL | -0.106 | -0.249 | +0.200 (110) |
| DOGE | MARGINAL | -0.068 | -0.234 | +0.697 (36) |

**Most reliable = the PASS trio (ETH, AVAX, TRX):** positive in full + test + WF at once.
The MARGINAL ones (BTC/XRP/DOGE) have a negative full or test -> a positive WF smells like
fold luck; treat them as observation.

**Caveats:** low WR (12-37%) -> fat tail, it depends on a few big winners; the WF almost
always picks **tp_r=0** (no TP, let it run), consistent with #9. Modest OOS n (36-110).
Moderate-positive confidence.

---

## R7 - Candle patterns as a filter (2026-06-04)

> A study of discriminating power (strategy-independent), 12 coins, 3 years, 1h.
> 6 patterns from Sentinel; metric = P(correct direction) with +/- 1 ATR barriers, H = 24h.
> `research/candle_patterns.py`. (~6500 events/coin; SE ~ 0.6pp.)

**Part 1 - Pattern ALONE = NO edge.** P(correct) between 49.0% and 50.8% across the 12
coins -> indistinguishable from 50% (chance). Confirms Sentinel and the "a pattern
guarantees nothing" thesis.

**The "volatile coins respect patterns more" hypothesis -> NOT supported (on 1h).**
Spearman respect vs volatility rho = **-0.48** (p=0.12): if anything, the LESS volatile
coins (BNB 0.71%, TRX 0.44%) respected them slightly more; the most volatile (SOL/AVAX/
DOT/LINK ~1.2%) landed in the middle/bottom. (Sentinel saw it on 15m -> it may depend on
the TF; 15m check pending.)

**Part 2 - Confirmers (lift in P, equal-weighted, consistency across coins):**

| Indicator | lift | consistency | reading |
|---|--:|--:|---|
| vwap_side (price on the right side of VWAP) | +1.5pp | 10/12 | best, but small |
| trend (price vs EMA50 aligned) | +1.1pp | 10/12 | consistent |
| vol_spike / high_vol | +0.5-0.8pp | 6-8/12 | noisy |
| **rsi_extreme** (reversal at oversold/overbought) | **-3.7pp** | 1/12 | **HURTS** |
| at_extreme (at support/resistance) | -0.8pp | 6/12 | does not help |

**Synthesis:** the pattern is worth something ONLY with the TREND (aligned with VWAP/EMA50
= continuation), never as reversion (extreme RSI and "at support" subtract). The lift is
marginal (~1-1.5pp) -> useful as a **confluence filter/boost on an existing trend strategy,
never as a primary signal**.

### R7b - 15m + SUI check (2026-06-04)

> Repeated on 15m (Sentinel's native TF) and added SUI (a strong case in Sentinel).
> `research/candle_patterns.py 15m`. Huge n (25k+ events/coin -> SE ~ 0.3pp).

**Pattern alone = zero edge, confirmed on 15m.** P(correct) 49.2-50.2% (noise at that n).

**The "volatile coins respect more" hypothesis -> BURIED (2 TFs).** 1h rho = -0.21
(p=0.48), 15m rho = +0.08 (p=0.79). SUI was high on 1h (50.7%, and the most volatile at
1.56%) but **average on 15m** (49.9%) -> Sentinel's case does not reproduce on honest data.
No respect vs volatility correlation on either.

**Confirmers (15m, consistent with 1h):** trend +1.2pp (11/13), vwap_side +0.9pp (11/13),
stack +0.8pp (11/13), vol_spike +0.7pp (12/13). Reversion subtracts again (rsi_extreme
-1.0, at_extreme -0.9).

**FINAL VERDICT:** candle patterns are NOT deployed. Alone they are noise; the only useful
confluence (trend alignment) is already captured by the trend strategies (ema/vwap/orb). A
~1pp lift does not justify the complexity. Documented and parked.
