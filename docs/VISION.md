# Oscilion - Vision

> **UPDATE 2026-06-03 - PIVOT.** Honest validation (12 coins x 3 years, net of
> costs) **ruled out the reversion thesis** in this document: it has no edge and
> its calibration is inverted. The edge was in the **BREAKOUT** (range
> momentum/breakout), not in the bounce, which is exactly the risk the "honest
> verdict" section flagged as decisive. See **`docs/FINDINGS.md`** for the thesis
> that replaced it and its results. The rest of this document stays as the
> historical record of the v1 hypothesis; the principles and the risk model still
> apply.

## What it is

A system that analyzes BTC, ETH, SOL and other cryptocurrencies to discover
**oscillation ranges** (horizontal and diagonal) and trade **intraday reversion**
with high conviction: enter near one edge of the range *with turn confirmation*,
exit at the opposite edge, and protect the trade with a stop computed against
stop sweeps.

**Frequency:** low (1-2 trades/day, or none when there is no clarity). Quality over
quantity.

## North star (where we are heading)

```
Calculator  ->  Live monitor + alerts  ->  Semi-auto bot  ->  100% auto bot  ->  Binance copy-lead
 (Phase 2-3)        (Phase 4-5)              (Phase 6)          (Phase 7)          (Phase 8)
```

The end value: a bot that trades on its own, with low drawdown, that others copy
while we pay/earn a commission (10-12%). That is why, from day 1: a bot-ready
architecture, controlled risk and an **auditable track record**.

## Principles (non-negotiable)

1. **Honesty before hope.** The system must be able to say *"do not trade today"*
   and *"this strategy has no edge"*. That is success, not failure.
2. **Full auditability.** Everything is stored (snapshots, predictions, decisions,
   trades, parameters). Without data there is no learning. The forward record is
   the real antidote to the self-deception of overfitting.
3. **Risk first.** Never risk more than 2% per trade. Survival matters more than
   return.
4. **Only what is predictable.** We trade range regimes / clean channels. Chaos is
   observed, not traded.
5. **Adapted per coin.** Nothing is treated the same: leverage, stops and size are
   calibrated to each coin's volatility.
6. **Iterate with evidence.** If v1 does not perform, diagnose with data and make
   targeted improvements; do not abandon blindly nor insist blindly.

## The core ideas

| Concept | Technical translation |
|---|---|
| Horizontal range | Bollinger / Keltner / VWAP bands / Donchian over S/R |
| Diagonal range (trend) | Linear regression channel |
| "Which coin respects its range?" | Hurst (<0.5), OU half-life, variance ratio, ADF -> **reversion score** |
| Regime | Range vs trend classifier (ADX, band width/stability) + volatility regime |
| Conviction | **Calibrated** 0-100% score (80% => historically ~80% hit rate) |
| Safe stop | Edge + beyond the sweep cluster + ATR buffer |
| Leverage | = 2% / stop_distance -> fixed risk, liquidation very far away |
| "Best entry" | Edge + **turn confirmation** (not in the middle of the range) |
| Exit in time | Momentum exhaustion detection + adverse breakout |

## The honest verdict (status: hypothesis to validate)

- **Building it: viable.** The strategy is legitimate and the risk management is
  better than the retail average.
- **Being profitable: not guaranteed.** It depends on a predictive edge that
  **only an honest backtest + forward test** can confirm. It may not exist after
  costs.
- **Key risk:** telling a *bounce* from a *breakout* live. That is where it is won
  or lost.
- **Realistic expectation:** a net Sharpe of ~1-1.5 on a subset of coins/regimes
  would be a good, tradeable result. It is not a money printer.

## Go / No-Go (decision gate)

Before risking real money, the system must pass:

- [ ] Walk-forward backtest **with real costs** (fees + funding + slippage) ->
      positive expectancy.
- [ ] **Calibrated** score (probabilities that hold up).
- [ ] Tolerable and stable maximum drawdown.
- [ ] Live **paper trading** consistent with the backtest.

If it passes -> small capital -> scale. If not -> diagnose, iterate, or pivot/stop
honestly.

## What we will NOT do

- Strategies **without a stop-loss** ("wait for price to come back"). A pretty curve
  until a black swan liquidates everything. That is hidden risk, not edge.
- Extreme leverage (minimum margin) for "efficiency". Liquidation gets dangerously
  close.
- Trust fixed past ranges. Everything is recomputed on a rolling window, in real
  time.
