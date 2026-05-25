"""PrecisionFilter — Phase F3.

Validates that the instrument's tick size and lot size are within acceptable
bounds for the strategy's order-placement precision.

NSE equity has a default tick of ₹0.05 and lot of 1 for cash equities.
F&O segments have larger lot sizes (typically 25–1500 shares per lot).
This filter is most useful for F&O universe construction — strategies with
fixed fractional sizing break when the lot is enormous relative to capital.

``max_lot_size`` defaults to 1 (cash-equity only).  Set to e.g. 500 to allow
mid-cap F&O names.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter


@dataclass
class PrecisionFilter(PairFilter):
    max_tick_size: float = 1.0   # INR
    max_lot_size: int = 1        # 1 = cash equity only

    name: str = "precision_filter"

    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        if snapshot.tick_size > self.max_tick_size:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=(
                    f"tick size ₹{snapshot.tick_size} > max ₹{self.max_tick_size} "
                    "(too coarse for target order precision)"
                ),
            )
        if snapshot.lot_size > self.max_lot_size:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=(
                    f"lot size {snapshot.lot_size} > max {self.max_lot_size} "
                    "(lot too large for capital allocation model)"
                ),
            )
        return FilterResult.ok(snapshot.symbol, self.name)
