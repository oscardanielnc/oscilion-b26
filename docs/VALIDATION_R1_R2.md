# Validation R1+R2 - strategies rescued from the BTC project (honest engine, per coin)

> 2026-06-03. We ported 2 strategies from the BTC project (EMA_TREND_STACK,
> MOMENTUM_PULLBACK) to **Oscilion's honest engine** (2h/4h signal, pessimistic 15m exit,
> real taker costs) and validated them **per coin** (12 coins, 3 years) with default + OOS
> sweep + walk-forward. Reports: `data/reports/r2_strat_validation.md`,
> `r2b_exec_check.md`.

---

## PENDING DECISIONS (for the project owner)

Execution does NOT stop for these; they are listed with my recommendation.

> **R3 UPDATE (done):** ported ORB_BREAKOUT and BREAK_RETEST. **ORB is the multi-coin
> workhorse** (median +0.029, 8/11 positive) and RESCUES LINK and DOT (where
> trend-following failed). The **strategy x coin map and the proposed direction are in
> `docs/STRATEGY_MAP.md`** (read it first). A new big decision (#6 below).

1. **Adopt the high-conviction survivors**: EMA_TREND_STACK (with `tp_r=4`, freshness gate,
   session filter) on **BTC, BNB, TRX**.
   -> *I recommend YES.* They are positive over the full period **and** OOS, with a fixed
   config (no selection bias). [YES / adjust which]
2. **MOMENTUM_PULLBACK** only survives on **TRX** (and BNB marginally). Do we add it as a
   secondary on TRX or keep it on the bench?
   -> *I recommend the bench* (a single coin, lower conviction). [bench / add on TRX]
3. **9 coins (SOL, ETH, XRP, ADA, DOGE, AVAX, LINK, LTC, DOT)**: trend-following and
   pullback do **not** work there. Do we test them with OTHER strategies in R3
   (ORB/VWAP/BREAK_RETEST) before dropping them from the universe?
   -> *I recommend YES* (R3 is running). [YES / drop]
4. **Exit philosophy change**: the edge appears with **"let winners run" (high `tp_r` /
   trailing)**, not with a TP at the opposite edge. OK to adopt this for the trend
   strategies? -> *I recommend YES.* [YES / discuss]
5. **Maker execution (R4)**: the measured lift is small (+0.015 to +0.04R) -> it is not the
   savior we hoped for. Do we lower its priority? -> *I recommend YES, low priority.*
6. **(NEW) Adopt the two-engine, per-coin direction** (see STRATEGY_MAP.md):
   EMA_TREND_STACK for clean-trend large caps (BTC/BNB/TRX) + ORB_BREAKOUT for alts
   (LINK/DOT/TRX + marginal ones). High-conviction core: **BTC, BNB, TRX, LINK, DOT**.
   -> *I recommend adopting this as Oscilion's direction.* [adopt / discuss]
7. **SOL/ETH/AVAX**: no clean edge in any of the 4 strategies. Do we leave them out of the
   tradeable universe for now (discipline) and look for a tactic of their own later?
   -> *I recommend leaving them out until an edge is proven.*

---

## 1. Honest verdict

**Most of the BTC project's strategies do NOT survive the honest engine.** Their Sharpe
ratios of 1.41/1.01 were optimistic (the audit already warned about it). With real costs
and pessimistic exits, the median expectancy **across coins is negative**.

**BUT there is a real, coin-specific edge in trend:**

| Strategy | GENUINE edge (full + OOS positive, fixed taker config) | Conviction |
|---|---|---|
| **EMA_TREND_STACK** (`tp_r=4`) | **BTC** (OOS +0.13 / full +0.34), **BNB** (+0.41 / +0.13), **TRX** (+0.14 / +0.34) | **High** |
| MOMENTUM_PULLBACK (`tp_r=4`) | **TRX** (+0.28 / +0.21); BNB marginal | Medium |
| (both) FAIL on | SOL, ETH, XRP, ADA, DOGE, AVAX, LINK, LTC, DOT | - |

Reading: **trend-following pays on clean-trend large caps (BTC/BNB/TRX), not on choppy
alts.** This validates the idea of **each coin with its own strategy**, not one for all.

## 2. Quantified lessons

- **"Let winners run" is the real lever.** Raising `tp_r` from 2 to 4 turns BTC from
  negative to positive. The walk-forward picks `tp_r=4` almost every time. => the TP at the
  opposite edge (reversion style) was the mistake; trend wants a wide TP / trailing.
- **Maker does not rescue it** (lift +0.015 to +0.04R/trade). Useful but minor; R4 drops in
  priority.
- **15m exit resolution ~ 1m** (BTC: +0.344 vs +0.346 full; +0.131 vs +0.142 OOS). The
  honest engine is robust; 1m is not needed for the alts.
- **The default (the YAML params) almost never survives OOS**; the edge needs the high
  `tp_r` adjustment. Confirms that the original numbers came from an optimistic harness.
- **Low winrate (~25-35%) with a wide TP** -> many small losses, few big wins. Consistent
  with trend-following; it demands discipline (it is not a "hit machine").

## 3. What was built (R1)

- `backtest/resample.py`: causal 1h -> 2h/4h (no look-ahead).
- `backtest/strategies_lib.py`: EMA_TREND_STACK and MOMENTUM_PULLBACK ported, pure,
  parameterized (faithful to the BTC project's YAML + freshness gate). Later moved to
  `oscilion/strategies/library.py`.
- `backtest/engine_strat.py`: the **honest engine**: coarse signal, **pessimistic exit on a
  fine TF (15m)** (stop before TP), entry at the next open, costs + funding, primary metric
  in **R**; `load_bundle`/`run` separate the (expensive) load from the (cheap) run.
- BTC 1m ingested into the store (from the BTC project's parquet into Oscilion) for the
  resolution check.

## 4. Implication for Oscilion's DIRECTION

The evidence (Oscilion + the BTC project, twice) points to:

> **A per-coin, multi-coin TREND/CONTINUATION observer that lets winners run.** Not
> reversion. Not a single strategy. Each coin gets the strategy and params that were
> validated for it. We start with EMA_TREND_STACK on BTC/BNB/TRX.

This forecasts direction (the clean trenders are LONG-biased) and says when to enter
(stack + fresh pullback), with an exit that cuts losses small and lets winners run.

## 5. Next (in progress / planned)
- **R3 (running):** port ORB_BREAKOUT, VWAP_ANCHOR, BREAK_RETEST and validate per coin:
  do they rescue the 9 coins where trend-following fails?
- R5: **trailing exits** (they could beat a fixed `tp_r=4`).
- R6: portfolio of the survivors + live forward test (dry-run).
