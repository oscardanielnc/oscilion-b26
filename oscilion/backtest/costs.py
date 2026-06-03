"""Modelo de costos reales (RISK_MODEL.md §7).

Un backtest sin costos miente. Aquí entran:
  • fees: maker (entrada/TP en límite) vs taker (stop/ruptura, urgente).
  • slippage: deslizamiento al cruzar el libro (solo en taker).
  • funding: el perp paga/cobra funding cada 8h mientras la posición vive.

Convención de funding: con tasa > 0 los LONG pagan y los SHORT cobran.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import config


@dataclass(frozen=True)
class CostModel:
    maker_fee: float = 0.0002          # 0.02% (límite post-only)
    taker_fee: float = config.taker_fee  # 0.036% (mercado)
    slippage_bps: float = 2.0          # 2 bps de deslizamiento en taker

    def fee(self, notional: float, *, maker: bool) -> float:
        return abs(notional) * (self.maker_fee if maker else self.taker_fee)

    def fill_price(self, price: float, side: str, *, is_entry: bool, maker: bool) -> float:
        """Precio efectivo de ejecución. Maker = sin slippage; taker = peor."""
        if maker:
            return price
        slip = price * self.slippage_bps / 10_000
        # comprar (long entry / short exit) paga más caro; vender, más barato
        buying = (side == "long" and is_entry) or (side == "short" and not is_entry)
        return price + slip if buying else price - slip

    def funding(self, notional: float, side: str, rate: float) -> float:
        """Costo de funding (positivo = lo paga el trader)."""
        sign = 1.0 if side == "long" else -1.0
        return abs(notional) * rate * sign


DEFAULT_COSTS = CostModel()
