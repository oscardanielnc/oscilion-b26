# Oscilion - Risk Model

The heart of the system. Every trade follows this math.

## 1. The master equation

```
Leverage (L) = Max_risk(%) / Stop_distance(%)
             = 2% / stop%
```

Automatic consequences (no numbers picked by hand):

| Property | Result | Why |
|---|---|---|
| Loss if the stop fires | **= 2% of the margin**, always | L * stop% = 2% |
| Gain if the target is hit | **= 2% * RR** | L * move% = 2% * (move/stop) |
| Distance to liquidation | **~50x the stop distance** | the stop sits at 2% of the way to liquidation |
| Leverage per coin | high on low-vol coins, low on high-vol coins | tight stop => large L |

> **Golden rule:** the user thinks in "I lose at most 2% / I make at least 5%". The
> system picks the leverage so that holds, whatever the stop distance is.

## 2. The RR >= 2.5 filter

Since `gain = 2% * RR`, a **+5%** target needs **RR >= 2.5** (the target at >= 2.5x
the stop distance).

```
profit% = 2% x RR
RR 2.5 -> +5%   |   RR 3 -> +6%   |   RR 4 -> +8%
```

**A coin whose setup does not offer RR >= 2.5 is NOT traded that day.** It is a
filter, not a preference.

## 3. Example per coin ($10k capital)

| Coin | Vol/day | Safe stop | L = 2%/stop | Target (RR>=2.5) | Max loss |
|---|---|---|---|---|---|
| BTC | ~1.5% | 0.5% | ~4x | +5% (move ~1.25%) | -2% |
| ETH | ~3% | 1.2% | ~1.7x | +5% (move ~3%) | -2% |
| Volatile alt | ~10% | 4% | ~0.5x | +5% (move ~10%) | -2% |

## 4. Anti-sweep stop

The obvious level (e.g. 100) is where stops get hunted. The stop does NOT go there.

```
   range: [100 -------------- 120]
                |
   obvious stop cluster ->  99-98  <- institutional sweep zone
                |
   SAFE STOP    ->  97.9   (beyond the cluster + ATR buffer)
```

Inputs to compute it: historical wicks that pierced and reverted, the liquidation/
stop map, the coin's typical noise (ATR). If the safe stop ends up further away ->
**L drops on its own**, and the loss stays at 2%. No extra risk cost.

## 5. Portfolio sizing (multi-coin)

The user picks up to ~3 coins from the top. Each keeps its -2%/+5% **on its own
margin**. Capital weight by:

```
weight_i ~ f( conviction_i , 1/volatility_i , correlation_among_chosen )
```

- **Conviction** (score) -> more capital to the most likely setup.
- **Volatility** -> less to the most erratic one.
- **Correlation** -> BTC/ETH/SOL move almost together. 3 correlated longs = **a
  single tripled bet**, not diversification. The system warns about it and adjusts.
- Method: **fractional Kelly** (caps the size by itself) with the proportional
  version shown as a reference.

Worst case (every trade hits its stop on the same day) ~ **-2% of total capital** if
100% deployed.

## 6. Dynamic TP

`+5%` is the **floor to enter**, not the ceiling. During the trade:
- If momentum has conviction to continue -> the target extends with a **trailing**
  stop.
- If momentum runs out halfway -> **warn / take partial profit**.
- The trailing stop moves to break-even as soon as the trade goes in our favor.

## 7. Maker vs taker (execution decision)

| Action | Urgent? | Order | Cost (USDC) | Rule |
|---|---|---|---|---|
| Entry at the edge | No | **Post-only** limit (maker) | 0% | If it does not fill, no trade. No harm. |
| Take-profit at target | No | Maker limit | 0% | Patient, waits for the price. |
| **Stop / adverse breakout** | **YES** | Market / taker | ~0.036% | **Exit now.** Never risk the fill to save a fee. |

Real measured cost = **fee + half spread** per coin (do not always assume USDC; use it
where it pays off).

> **Never sacrifice the execution certainty of a stop to save a commission.** 0.036%
> is cheap insurance against a loss of 2% or more.
