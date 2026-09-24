"""Real cost model (RISK_MODEL.md section 7).

A backtest without costs lies. Included here:
  - fees: maker (limit entry/TP) vs taker (stop/breakout, urgent).
  - slippage: crossing the book (taker only).
  - funding: the perpetual pays/receives funding every 8h while the position lives.

Funding convention: with a rate > 0, LONGs pay and SHORTs receive.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import config


@dataclass(frozen=True)
class CostModel:
    maker_fee: float = 0.0002          # 0.02% (post-only limit)
    taker_fee: float = config.taker_fee  # 0.036% (market)
    slippage_bps: float = 2.0          # taker slippage

    def fee(self, notional: float, *, maker: bool) -> float:
        return abs(notional) * (self.maker_fee if maker else self.taker_fee)

    def fill_price(self, price: float, side: str, *, is_entry: bool, maker: bool) -> float:
        """Effective fill price. Maker = no slippage; taker = worse price."""
        if maker:
            return price
        slip = price * self.slippage_bps / 10_000
        # buying (long entry / short exit) pays more; selling receives less
        buying = (side == "long" and is_entry) or (side == "short" and not is_entry)
        return price + slip if buying else price - slip

    def round_trip_cost_r(self, stop_pct: float) -> float:
        """Estimated round-trip cost in R units for a stop at `stop_pct`.

        Assumes taker on entry and exit (worst case = the trade dies at the stop).
        Fees and slippage are ~constant in price terms, but the notional
        (= risk / stop_pct) grows as the stop tightens, so the cost in R dominates
        with tight stops:
            cost_R = (2 * taker_fee + slippage) / stop_pct
        Matches the `cost_audit` breakdown (r_fee_entry + r_fee_exit + r_slip).
        """
        if stop_pct <= 0:
            return float("inf")
        return (2 * self.taker_fee + self.slippage_bps / 10_000) / stop_pct

    def funding(self, notional: float, side: str, rate: float) -> float:
        """Funding cost (positive = paid by the trader)."""
        sign = 1.0 if side == "long" else -1.0
        return abs(notional) * rate * sign

    def realized(self, side: str, entry: float, exit_px: float, notional: float,
                 entry_fee: float, *, maker_exit: bool, funding_total: float = 0.0):
        """Net PnL of a closed trade (SINGLE SOURCE used by the engine and monitor):
        exit fill (slippage if taker) + fees on both sides + funding.
        Returns (pnl, exit_fill)."""
        exit_fill = self.fill_price(exit_px, side, is_entry=False, maker=maker_exit)
        price_ret = (exit_fill - entry) / entry if side == "long" else (entry - exit_fill) / entry
        pnl = price_ret * notional - (entry_fee + self.fee(notional, maker=maker_exit)) - funding_total
        return pnl, exit_fill


DEFAULT_COSTS = CostModel()
