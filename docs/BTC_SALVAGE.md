# Rescuing the BTC/Sentinel project - what is useful to us

> A thorough review of an earlier local research project (`btc/`, the `sentinel` system,
> discarded after its 2026-05-29 audit). Goal: extract data, strategies, lessons and
> reusable tactics for Oscilion (a multi-coin observer that forecasts direction and says
> when to enter). Review date: 2026-06-03.

---

## 0. Review conclusion

The BTC project **independently reached the same conclusions as Oscilion**, with different
code, different strategies and a different methodology. That raises confidence a lot:

| Finding | Oscilion | BTC/Sentinel |
|---|---|---|
| Mean reversion | no edge (PF 0.76, inverted calibration) | BB_REVERSION Sharpe -0.62/-0.73 |
| Momentum / breakout / continuation | OOS edge (regime-conditional) | EMA_STACK, MOMENTUM_PULL, ORB, VWAP, BREAK_RETEST positive OOS |
| Raw edge ~breakeven, **costs decide** | yes | yes (audit: #1 lever = maker execution) |
| **Conviction/score does NOT predict** edge | yes (inverted calibration) | yes ("sizing by conviction is noise") |
| Management that cuts winners hurts | (pending) | yes (hold-to-T2 > partial + breakeven + trail) |

**There is a lot to rescue**: 5+ years of data, a library of strategies with results, and
dozens of lessons already paid for with work. **The big asterisk:** the strategies'
positive backtests came from sentinel's own harness, which its audit found to be
**optimistic** on other tactics (vpoc/mttc/srb gave -0.127R when measured with an honest
engine). => **those strategies must be re-validated with Oscilion's honest engine** before
believing them.

---

## 1. Reusable data (high value, ready)

`btc/backtest/data/`

| Dataset | Coverage | Use |
|---|---|---|
| `futures_um/BTCUSDT_1m.parquet` (120 MB) | 2021-2026, 1 minute | **Gold**: honest intrabar exits (SL before TP) |
| `futures_um/BTCUSDT_{5m,15m,1h,4h}.parquet` | 2021-2026 | multi-TF signals |
| `futures_um/BTCUSDT_funding.parquet` | history | real funding cost |
| `{14 alts}_1h_730.csv` + `_15m.csv` | 730 days | aave, ada, apt, avax, bnb, doge, dot, eth, inj, link, sol, sui, xrp |

-> Oscilion already downloads its own history via ccxt; this data serves as a **cross
source / verification** and for the 1m exit engine (which Oscilion does not have yet).

---

## 2. Documented strategies (the jewel) - TRAIN/TEST 2023-2026

Results from sentinel's harness (to be re-validated honestly). Sorted by interest:

| Strategy | Type | TEST Sharpe | TEST avg R / WR | Direction | Note |
|---|---|---:|---|---|---|
| **EMA_TREND_STACK** | trend | **1.41** | +0.68R / 60% | LONG-only | 9>21>50 4H stack + pullback to EMA21 |
| **MOMENTUM_PULLBACK** | continuation | **1.01** | +0.14R / 54% | LONG-only | 2H impulse + 10-80% pullback, TP=2R |
| **VWAP_ANCHOR** | trend | 0.92 | +0.22R / 40% | LONG-only | price > 1H and 4H VWAP, TP=2.5R |
| **BREAK_RETEST** | continuation | 0.85 | +0.85R / 50% | long+short | **stealth** breakout (low vol) + retest, small n |
| **ORB_BREAKOUT** | breakout | 0.83 | +0.26R / 47% | long+short | breaks a narrow 6H range, EU/NY session |
| BB_REVERSION | reversion | -0.62 | / 34% | - | loses except in a rare sideways regime |

**Reading:** the first 5 are **momentum/trend/continuation** -> aligned with Oscilion's
pivot. The only **contrarian** one (BB_REVERSION) loses, just like Oscilion's reversion.
Source code in `btc/sentinel/strategies/*.py`.

---

## 3. Transferable lessons (tactics paid for with work)

1. **Enter FRESH, before the crowd confirms.** A gate repeated and validated across
   several strategies: if the 1H EMA9/21 is **already** aligned -> late entry, worse R:R.
   (`O1_gate` / inverted `C3`). It is a real *timing* edge. => test it in Oscilion.
2. **Many standard indicators are "null filters"** (RSI, MACD): about the same activation
   on winners and losers. Do not trust them without measuring discriminating power.
3. **Costs decide.** Raw edge ~breakeven; **maker** execution is the #1 lever (same as
   Oscilion). A limit/retest entry design lowers the drag.
4. **Conviction != edge.** Sizing by "conviction" was noise (= inverted calibration).
5. **Regime dependence:** breakout/momentum shine in volatile / range-then-breakout
   markets; they flatten in smooth trends. Reversion only works sideways (= Oscilion).
6. **Exits per strategy:** MOMENTUM_PULL improves a lot with TP=2R; ORB gets worse with a
   TP (let winners run). There is no single exit; it depends on the tactic.
7. **Directional bias:** BTC LONG-only (structural bullish bias; SHORT destroyed capital in
   trend strategies). ORB does use SHORT (range breakout in volatile markets).
   => the optimal direction is **conditional on the asset/regime** (key to "forecasting
   direction").
8. **Session:** Europe/NY pay off; Asia generates whipsaws. Toxic windows: 22-23 UTC,
   the Friday CME close, +/-1h around macro news (CPI/FOMC/NFP).
9. **Management:** cutting winners (partial @ T1 + breakeven + trail) subtracted;
   hold-to-T2 added.
10. **Patterns (contextual signals)** with documented conditions (index + skip_when):
    FUND_EXT (first spike, neutral RSI), LIQ_SWEEP (needs an aligned 4H), SESSION_BREAK
    (counter-trend Asia breakout 75%), ROUND_MAG, CME_GAP. Weak/contextual edge: useful as
    **filters/boosts**, not as a primary signal.

### Already rejected with evidence (do NOT re-investigate blindly)
GARCH/ATR sizing (OOS 0.025), OU/VA-return (no edge), Kelly (insufficient N), standalone
OB imbalance (no edge), liq-stream CVD proxy (OOS 0.21), sizing by conviction.
5-state HMM: sophisticated but it **did not create edge** by itself (the system stayed
negative).

---

## 4. Methodology worth inheriting
- **Primary metric = expectancy per trade (R)**, not compounded %.
- **Pipeline:** isolate -> OOS backtest >= 0.70 -> joint backtest -> production.
- **Pessimistic 1m exit engine** (SL before TP within the same minute) + real costs.
  Oscilion today resolves intrabar with the base candle; BTC's 1m data would raise realism.

---

## 5. What to rescue vs discard

| Rescue | Discard / archive |
|---|---|
| BTC 1m/funding data + 14 alts | sentinel's production stack (HMM, tournament, OI, Kalman): complex and no net edge |
| The logic of the 5 momentum/trend strategies | BB_REVERSION (contrarian, loses) |
| Lessons 1-10 (esp. freshness gate, costs, exits) | Weak-edge patterns as a primary signal |
| Methodology (R, OOS >= 0.7, pessimistic 1m engine) | Conclusions from the optimistic harness without re-validation |

---

## 6. Hypotheses to validate (honestly, in Oscilion)

| # | Hypothesis | Test |
|---|---|---|
| H1 | The momentum/trend strategies keep a **positive expectancy under an honest engine** (real costs, pessimistic 1m exit) on 12 coins | port to a `breakout_candidate`-style + honest engine, OOS |
| H2 | The **freshness gate** (enter before the 1H EMA confirms) adds a **generic** edge (not just BTC) | A/B with and without the gate, per coin |
| H3 | **Maker execution** turns thin edges into solid ones | model limit fills (no-fill / adverse selection) |
| H4 | The **optimal direction** is conditional (LONG-only by bias, or regime-dependent) | measure long vs short per coin/regime |
| H5 | The **optimal exit** depends on the tactic (2R TP vs trailing vs hold) | exit grid per strategy |
| H6 | Combining **weakly correlated survivors** raises the portfolio Sharpe | multi-coin portfolio |
| H7 | A **regime filter** (Oscilion's range/trend) improves each strategy | condition on regime |
| H8 | The **session filter** (EU/NY) generalizes beyond BTC | A/B per session |

---

## 7. Focus (do not lose it)

Oscilion = a **constant multi-coin observer** that forecasts direction (up/down) and says
**exactly when to enter**, with the highest possible conviction and **knowing when to exit
in time** (even if it does not reach +5%; what matters is getting the direction right and
managing risk). Rescuing the BTC project serves that focus: it brings **directional
strategies validated in one direction** (momentum/continuation) and execution/timing
lessons, exactly what turns "we have a thin edge" into "we know when and how to enter".

> The multi-session test plan is in `docs/ROADMAP.md` (section "Testing phase - rescuing
> the BTC/Sentinel project").
