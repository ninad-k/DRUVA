"""RangeStabilityFilter — Phase F3.

Filters out instruments whose ATR(14) as a percentage of close (``atr_pct``)
is either too wide (erratic / news-driven) or too narrow (illiquid / halted).

Typical intraday range: 0.5% – 8%.  Anything outside either bound is
problematic: hyper-volatile names blow SLs on noise; flat names never reach
TP and eat spread costs on every round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.scanner.filters.base import FilterResult, InstrumentSnapshot, PairFilter


@dataclass
class RangeStabilityFilter(PairFilter):
    min_atr_pct: float = 0.3   # reject ultra-flat names
    max_atr_pct: float = 10.0  # reject hyper-volatile names

    name: str = "range_stability_filter"

    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        if snapshot.atr_pct < self.min_atr_pct:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=(
                    f"ATR% {snapshot.atr_pct:.2f}% < min {self.min_atr_pct:.2f}% "
                    "(instrument may be halted or illiquid)"
                ),
            )
        if snapshot.atr_pct > self.max_atr_pct:
            return FilterResult.reject(
                snapshot.symbol,
                self.name,
                reason=(
                    f"ATR% {snapshot.atr_pct:.2f}% > max {self.max_atr_pct:.2f}% "
                    "(instrument too erratic)"
                ),
            )
        return FilterResult.ok(snapshot.symbol, self.name)
