"""Base types for the pair-list / universe filter chain — Phase F3.

Each ``PairFilter`` receives an ``InstrumentSnapshot`` — a lightweight
struct bundling the instrument metadata with recent OHLCV statistics already
pre-computed (so individual filters don't need to re-iterate candles).
The ``FilterPipeline`` (``pipeline.py``) builds these snapshots and fans out
to all registered filters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class InstrumentSnapshot:
    """Pre-computed stats for one instrument, passed to every filter.

    All price-related fields are in INR.  ``avg_daily_turnover_inr`` is the
    median daily value-traded over ``lookback_days`` (volume × VWAP proxy).
    ``atr_pct`` is ATR(14) expressed as a percentage of the current close.
    ``listing_date`` is the date the instrument was first traded on the exchange
    (used by the age filter).
    """

    symbol: str
    exchange: str
    close: float
    avg_daily_turnover_inr: float = 0.0
    atr_pct: float = 0.0
    listing_date: date | None = None
    tick_size: float = 0.05
    lot_size: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterResult:
    """Decision returned by a single filter for one instrument."""

    passed: bool
    symbol: str
    filter_name: str
    reason: str = ""

    @classmethod
    def ok(cls, symbol: str, filter_name: str) -> "FilterResult":
        return cls(passed=True, symbol=symbol, filter_name=filter_name)

    @classmethod
    def reject(cls, symbol: str, filter_name: str, reason: str) -> "FilterResult":
        return cls(passed=False, symbol=symbol, filter_name=filter_name, reason=reason)


class PairFilter(ABC):
    """Abstract pair-list filter."""

    name: str = "pair_filter"

    @abstractmethod
    def apply(self, snapshot: InstrumentSnapshot) -> FilterResult:
        """Return a ``FilterResult`` for the given instrument snapshot."""
