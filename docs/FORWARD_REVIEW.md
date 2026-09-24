# Forward review - first real cycle (paper)

> Log of the live forward (dry-run) reviews and the open points to resolve.
> Last review: **2026-06-12** (data from 10-12 June). Times in UTC-5.

## Status as of 2026-06-12 (deployment CONFIRMED live)

- **Infrastructure:** healthy. `errors: []` across the whole window; closes with
  `cost_audit` populated (schema v6 deployed and working), stops exit at **exactly**
  -1.04R per the model -> no hidden cost, exit slippage was already modeled (confirmed
  with data).
- **2 trades closed in the window**, both **PRE-GATE**:

| # | Symbol | Strategy | Side | R | Entry | Close |
|---|---|---|---|---|---|---|
| 1 | DOGE | vwap_anchor | long | -1.04 | 10-Jun 09:00 | stop |
| 2 | ETH  | vwap_anchor | long | -1.04 | 10-Jun 09:00 | stop |

  > The entries (09:00) are **earlier** than the gate commits (`10c1c8e` 09:22,
  > `033e52c` 10:17 the same day). They do not count as gated evidence. The current gate
  > **would have vetoed DOGE** (local backtest exp_R -0.077). They are leftovers of the
  > old process.

- **1 POST-GATE (legitimate) entry:** AVAX/vwap_anchor long (12-Jun 12:00), local
  backtest n=188 / exp_R +0.135 -> it correctly passes the gate. **Still open** (not
  closed yet).
- **The rest of the series are WAITING**: the gate filters, it does not sleep.

### Cumulative forward (whole period, 06-08 -> 06-12)
**7 closed trades, 1 winner (TRX ORB +0.22), ~ -6.2R, ALL pre-gate.**
The "clean" gated sample today is **1 open trade** -> statistically zero information.
**The -6.2R does not refute the edge**: it is a process leak that was already fixed, not
a market signal.

### Observations to watch
- **`vwap_anchor` is 0/5 in forward** (the weakest leg of the backtest). The gate already
  cuts DOGE (-0.077) and XRP (-0.114), but **ETH passes with exp_R +0.022** -> noise, not
  edge. **Proposal:** raise `OSCILION_GATE_MIN_EXP_R` from 0.0 to **+0.05/+0.10** (~ the
  round-trip cost) so only what pays its fees with margin trades. (1 line / env var, no
  code.)
- **Pace ~0.5 trades/day post-gate -> 50 gated trades ~ 3 months.** If that is too slow,
  the safe lever is **widening the universe within already validated combos** (more
  symbols with local n >= 30), never loosening the gate.
- The goal of the previous sprint (that the process stops giving away R) is **met and
  verified in production**.

## Status as of 2026-06-10

- **Infrastructure:** healthy. `errors: []`, restarts OK, trade close logging **now
  works** (`trades` + `trade_summary` populated; it was missing before).
- **First cycle closed:** 5 trades.

| # | Symbol | Strategy | Side | R | PnL | Close |
|---|---|---|---|---|---|---|
| 1 | TRX | orb_breakout | short | +0.25 | +$50 | timeout |
| 2 | TRX | vwap_anchor | long | -1.13 | -$226 | stop |
| 3 | TRX | break_retest | long | -1.10 | -$220 | stop |
| 4 | DOGE | vwap_anchor | long | -1.04 | -$208 | stop |
| 5 | DOGE | vwap_anchor | long | -1.04 | -$209 | stop |

**Net: -4.07R, -$814, win rate 20% (1/5).** Paper, no real capital. Tiny n -> not
conclusive, but the signal points in an uncomfortable direction.

## Findings

1. **Zero TPs reached.** 4/5 at a full stop; the only green one was a timeout (+0.25R),
   not the target. The *let winners run* thesis did not materialize once. A dangerous
   pattern: cut small green, lose full red.
2. **Stops realize worse than -1R** (-1.04 to -1.13R). The anti-sweep buffer + taker
   execution costs 4-13% on top of the planned 1R. Suspicion: the honest backtest may NOT
   model this exit slippage -> inflated theoretical edge.
3. **`vwap_anchor` is the bleeder** (3 trades, 0% WR, -1.07R). And **DOGE/vwap_anchor
   entered twice live with a backtest n=1** (exp_R -3.46, no validation). It re-entered
   the same losing setup. A process leak.
4. **Correlated concentration:** TRX took vwap LONG + break_retest LONG at the same time,
   same direction -> 2x size on the same bet; both stopped out almost simultaneously.
   (The time before, 06-08 June, was the reverse: SHORT + LONG at the same time on TRX at
   almost the same price -> net exposure ~ 0 while paying double cost.)

### Backtest vs forward (early signal = red, tiny n)
| Combo | Backtest exp_R | Forward exp_R |
|---|---|---|
| TRX break_retest | +1.23 | -1.10 (n=1) |
| TRX vwap_anchor | +0.22 | -1.13 (n=1) |
| TRX orb_breakout | +0.18 | +0.22 (n=1) |
| DOGE vwap_anchor | -3.46 (n=1) | -0.82 (n=2) |

## Resolved points (2026-06-10, design + implementation)

1. **Universe gate by validation** -> `live/guards.gate_decision` +
   `db.get_forward_backtest`. Chosen design: the gate reads the **LOCAL backtest**
   (`forward_results` scope=backtest, the honest engine over THIS machine's data), not
   research numbers: the DOGE/vwap case was exactly "research says n=36, the VM only has
   n=1". Thresholds: `n >= 30` **and** `exp_R > 0` (`OSCILION_GATE_MIN_N` /
   `OSCILION_GATE_MIN_EXP_R`). If it does not pass -> the trade is **demoted to observe**
   (virtual, no capital, `trades.observe=1`, excluded from PnL): it keeps accumulating
   stats so it can graduate, but it does not bleed. It self-corrects as history grows.
2. **Cross veto per symbol** -> `guards.capital_position_on_symbol`: max **1 position WITH
   capital per symbol** (any strategy and direction). Observe does not block nor get
   blocked (no capital). Portfolio netting was discarded as over-engineering with 9 coins.
3. **Exit slippage audit** -> finding: monitor and backtest use the SAME
   `CostModel.realized` => the -1.04/-1.13R **is modeled** (it is 2bps slippage + fees +
   funding, not a hidden cost). To verify it with data, every close persists
   `trades.cost_audit` (JSON): R broken down into `r_gross` (pure price), `r_slip_exit`,
   `r_fee_entry/exit`, `r_funding`, visible in `/trades` and in the daily export. If, once
   there are real fills, observed slippage exceeds the modeled one, `costs.py` is
   recalibrated.
4. **`tp = 1e+18`** -> removed. Runner = `tp None` in strategies/position/DB/alerts ("tp
   runner"); internally `tp_barrier()` uses +/-inf, which never fires nor pollutes sizing.

   Extras from the same change: a **stop floor** `min_stop_pct` 0.2% (fixed risk /
   stop->0 blew up the notional; applied identically in monitor and engine) and a **stale
   signal guard** `max_signal_age_min` 30m (after downtime or a failed refresh it does not
   enter at an old price; the likely cause of the out-of-session ORB: the filter evaluates
   the CANDLE's time, not the current time).

5. **Block A (same session, second batch):** the **phase B limits are finally enforced
   live** (max 3 capital positions, max 2 per cluster; the portfolio was validated with
   that scheme but the monitor did not enforce it: 7 x 2% = 14% could open at once in a
   ~0.7-correlated cluster); **a real daily brake** (`max_daily_loss` 6% was in the config
   and never checked -> now a closed PnL for the UTC day <= -6% blocks new capital entries
   + a CRITICAL ntfy alert); **explicit ccxt timeout** (10s, `OSCILION_CCXT_TIMEOUT_MS`) + a
   slow-tick WARN; and the monitor state is **only persisted after a successful step**
   (before, a `finally` saved a possibly corrupt state that a restart would rehydrate).

## Open points

- Accumulate >= 50 forward trades from the gated core before any edge verdict.
- If real execution arrives (paper -> live): compare real fills vs the modeled
  `cost_audit` and recalibrate stop slippage if the real one is worse.

## Review history
- **2026-06-08** (data 06-08 Jun): 2 open TRX entries, no closes. Detected: opposite
  positions on the same symbol, `tp=1e+18`, mono-TRX (the rest WAITING), missing close
  logging.
- **2026-06-10** (data 08-10 Jun): first cycle of 5 closed trades (-4.07R).
- **2026-06-12** (data 10-12 Jun): deployment confirmed live (cost_audit populated, 0
  errors); 2 pre-gate closes (DOGE/ETH vwap -1.04R each); first legitimate gated entry
  (AVAX, open). Cumulative 7 closed ~ -6.2R, all pre-gate. The edge verdict is still
  pending a gated sample.
