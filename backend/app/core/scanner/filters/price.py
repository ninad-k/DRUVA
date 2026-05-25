"""PriceFilter — Phase F3.

Gates instruments to a configured price band.  Default: ₹10–₹100,000.

Sub-₹10 penny stocks have extreme bid-ask spreads relative to price; anything
above the upper bound is typically reserved for specific strategy types
(e.g. options on high-priced names) and should be opt-in.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter


@dataclass
class PriceFilter(PairFilter):
    min_price: float = 10.0
    max_price: float = 1_00_000.0

    name: str = "price_filter"

    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        if snapshot.close < self.min_price:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=f"close ₹{snapshot.close:.2f} < min ₹{self.min_price:.2f}",
            )
        if snapshot.close > self.max_price:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=f"close ₹{snapshot.close:.2f} > max ₹{self.max_price:.2f}",
            )
        return FilterResult.ok(snapshot.symbol, self.name)
