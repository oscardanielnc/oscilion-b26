# Strategy x coin map - what works, where (honest validation R2+R3)

> 2026-06-03. 4 strategies ported from the BTC project, validated on Oscilion's honest
> engine (2h/4h/1h signal, pessimistic 15m exit, real taker costs), **per coin**, 12 coins
> x 3 years. Metric: expectancy per trade in R. "Genuine" = positive over the full period
> **and** OOS (unbiased config) + confirmed in walk-forward. Reports:
> `data/reports/r2_*.md`, `r3_*.md`.

> Note added at closing: these backtest results did not hold in the live forward test;
> see `docs/AUDIT_2026-08-03.md`, section 3.

---

## 1. Result per coin (best strategy with a genuine edge)

| Coin | Best strategy | full / OOS / WF (exp_R) | Conviction | Notes |
|---|---|---|:--:|---|
| **TRX** | EMA_STACK, ORB, momentum | several positive (ORB +0.18/+0.29/+0.36) | very high | clean trend AND breakout |
| **LINK** | **ORB_BREAKOUT** | +0.20 / +0.31 / +0.23 | high | trend-following failed here |
| **DOT** | **ORB_BREAKOUT** | +0.13 / +0.10 / +0.19 | high | trend-following failed here |
| **BNB** | **EMA_TREND_STACK** (tp4) | +0.13 / +0.41 / +0.11 | high | clean trender |
| **BTC** | **EMA_TREND_STACK** (tp4) | +0.34 / +0.13 / +0.16 | high | ORB also marginally positive |
| ADA | ORB_BREAKOUT | +0.25 / +0.04 / +0.02 | medium-low | strong full, weak OOS |
| DOGE | ORB_BREAKOUT | +0.02 / +0.05 / +0.03 | low | marginal |
| XRP | ORB / break_retest | marginal (~+0.05 OOS) | low | marginal |
| LTC | ORB_BREAKOUT | mixed (WF +0.05) | low | marginal |
| SOL | - | no clean edge | none | revisit with other tactics |
| ETH | - | no clean edge | none | revisit with other tactics |
| AVAX | - | no clean edge | none | ORB def_test high but small n = noise |

## 2. Result per strategy (equal-weighted median across coins)

| Strategy | median exp_R | coins + / total | genuine (full+OOS+WF) | reading |
|---|---:|:--:|---|---|
| **ORB_BREAKOUT** | **+0.029** | 8/11 | TRX, LINK, DOT | the multi-coin workhorse (alts) |
| EMA_TREND_STACK (tp4) | ~0 (coin-specific) | 5/12 | BTC, BNB, TRX | for clean-trend large caps |
| MOMENTUM_PULLBACK | -0.086 | 3/12 | TRX | TRX only; low priority |
| BREAK_RETEST | -0.161 | 4/12 | TRX (small n) | discard (except TRX, with caution) |

## 3. Conclusion - Oscilion's direction

**Oscilion = a multi-coin observer that assigns EACH coin the strategy that was validated
for it, lets winners run, and only trades where there is a proven edge.** Two core engines:

1. **EMA_TREND_STACK** (high tp_r / trailing) -> **clean-trend** large caps: BTC, BNB, TRX.
2. **ORB_BREAKOUT** (breaks a narrow range, EU/NY session, 4h EMA50, freshness gate) ->
   **alts** (the workhorse, positive median): LINK, DOT, TRX + marginal ones.

This **confirms and refines Oscilion's own pivot**: ORB is exactly "a strong narrow range
breakout", the breakout edge Oscilion had already found, now with filters (range < 1.5%,
session, EMA50, freshness) that improve it and extend it to alts.

**Coins without a clean edge (SOL, ETH, AVAX):** not traded until a tactic of their own is
found (future sessions). Discipline: no edge, no trading on that coin.

## 3b. Exits - fixed TP vs trailing (R5)
Tested a fixed `tp_r=4` TP vs ATR trailing (1.5/2/3) with a fixed entry, per coin:
- **EMA_TREND_STACK -> a wide fixed TP (tp_r=4) wins**; trailing unravels it (BTC/BNB/TRX
  better with fixed).
- **ORB_BREAKOUT -> 2-3 ATR trailing is competitive or better OOS** on DOT, ADA, DOGE;
  comparable on LINK/TRX. Differences within the noise.
- Decision: **fixed `tp_r=4` as the base** for both; trailing = a future tweak for ORB.
  Report: `data/reports/r5_exit_check.md`.

## 4. Consolidated lessons (R1-R3)
- **Letting winners run** (high tp_r / no TP + timeout) beats a TP at the opposite edge.
- **The strategy depends on the coin's character:** trend-stack does not work on choppy
  coins; ORB does. There is no single strategy for all.
- **Maker rescues little** (+0.015-0.04R) -> R4 is low priority.
- **15m exit ~ 1m** -> the honest engine is robust.
- **BREAK_RETEST and MOMENTUM_PULLBACK** add little outside TRX -> not core.
- The **BTC project's Sharpe ratios were optimistic**; under the honest engine the edge is
  real but smaller and **coin-specific**, which is why validating per coin was key.

## 5. Pending decisions / next steps
See `docs/VALIDATION_R1_R2.md`, "PENDING DECISIONS". Next:
- **R5 - trailing exits** (they could beat the fixed tp_r on both engines).
- **R3b - VWAP_ANCHOR** (another trender; does it add anything over EMA_STACK?). Optional.
- **R6 - portfolio** of the genuine ones (BTC/BNB/TRX trend + LINK/DOT/TRX breakout),
  correlation, and a **live forward test (dry-run)**.
- Find a tactic for SOL/ETH/AVAX or exclude them honestly.
