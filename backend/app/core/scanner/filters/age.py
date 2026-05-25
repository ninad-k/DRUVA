"""AgeFilter — Phase F3.

Rejects recently-listed instruments that don't yet have enough price history
for reliable indicator computation or backtesting.

Default: require at least 365 days of trading history.  Fresh IPOs within
their first year are notoriously erratic — institutional lock-ins expire,
anchor investors unwind, and pre-IPO shareholders sell; none of which is
captured in a typical technical model trained on mature names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter


@dataclass
class AgeFilter(PairFilter):
    min_listing_days: int = 365
    """Minimum days since listing date.  Instruments with no listing date are
    allowed through (we can't reject what we don't know)."""

    name: str = "age_filter"

    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        if snapshot.listing_date is None:
            return FilterResult.ok(snapshot.symbol, self.name)
        age_days = (date.today() - snapshot.listing_date).days
        if age_days < self.min_listing_days:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=(
                    f"listed {age_days} days ago < min {self.min_listing_days} days "
                    f"(listed {snapshot.listing_date})"
                ),
            )
        return FilterResult.ok(snapshot.symbol, self.name)
