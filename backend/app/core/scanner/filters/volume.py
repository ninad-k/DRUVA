"""VolumeFilter — Phase F3.

Rejects instruments whose average daily INR turnover falls below
``min_turnover_inr``.  Default 5 Cr (₹50,000,000) is appropriate for
intraday strategies; position-trading strategies may lower this.

Thin-volume names wreck fills — even a single 1-lot order can move the price
by several ticks, making backtested edge disappear live.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter


@dataclass
class VolumeFilter(PairFilter):
    min_turnover_inr: float = 5_00_00_000.0   # ₹5 Cr default

    name: str = "volume_filter"

    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        if snapshot.avg_daily_turnover_inr >= self.min_turnover_inr:
            return FilterResult.ok(snapshot.symbol, self.name)
        return FilterResult.reject(
            snapshot.symbol,
            self.name,
            reason=(
                f"avg daily turnover ₹{snapshot.avg_daily_turnover_inr:,.0f} "
                f"< min ₹{self.min_turnover_inr:,.0f}"
            ),
        )
