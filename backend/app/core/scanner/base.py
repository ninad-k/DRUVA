"""Base classes for universe-wide scanners.

A :class:`Scanner` runs on a cadence (daily/weekly), iterates the universe,
and emits :class:`ScanCandidate` rows. These are persisted as ``ScanResult``
and surface in the Scanner Dashboard. Users promote candidates into real
orders through the existing ``ApprovalService``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.strategies.base import Candle


@dataclass(frozen=True)
class InstrumentRef:
    symbol: str
    exchange: str
    sector: str | None = None
    industry: str | None = None
    isin: str | None = None


@dataclass(frozen=True)
class FundamentalSnapshotDTO:
    """Point-in-time fundamentals as seen by a scanner."""

    symbol: str
    exchange: str
    roe: Decimal | None = None
    roce: Decimal | None = None
    eps: Decimal | None = None
    sales_growth_3y: Decimal | None = None
    profit_growth_3y: Decimal | None = None
    debt_to_equity: Decimal | None = None
    promoter_holding: Decimal | None = None
    market_cap: Decimal | None = None
    pe_ratio: Decimal | None = None
    sector: str | None = None
    industry: str | None = None


@dataclass(frozen=True)
class MarketCycleDTO:
    regime: str  # "bull" | "neutral" | "bear"
    nifty_roc_18m: Decimal | None
    smallcap_roc_20m: Decimal | None
    suggested_allocation_pct: Decimal


@dataclass(frozen=True)
class ScanCandidate:
    """A per-symbol candidate emitted by a Scanner."""

    symbol: str
    exchange: str
    score: float  # 0.0 – 1.0 (rich scanners may exceed via boosts; clamped before persist)
    stage: str = ""  # e.g. "stage_3", "sip_tranche"
    reason: str = ""
    suggested_entry: Decimal | None = None
    suggested_stop: Decimal | None = None
    suggested_target: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ScanContext(Protocol):
    """What the runner exposes to scanners at execution time."""

    account_id: UUID

    async def get_universe(self, filters: dict[str, Any] | None = None) -> list[InstrumentRef]:
        ...

    async def get_candles(
        self, symbol: str, exchange: str, timeframe: str, limit: int,
    ) -> list[Candle]:
        ...

    async def get_fundamentals(
        self, symbol: str, exchange: str,
    ) -> FundamentalSnapshotDTO | None:
        ...

    async def get_market_cycle(self) -> MarketCycleDTO | None:
        ...

    async def emit(self, candidate: ScanCandidate) -> None:
        ...


class Scanner(ABC):
    """Abstract scanner — runs on a cadence, emits candidates."""

    id: UUID | None
    account_id: UUID | None
    parameters: dict[str, Any]

    def __init__(
        self,
        *,
        id: UUID | None = None,
        account_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.account_id = account_id
        self.parameters = parameters or {}

    async def on_start(self, context: ScanContext) -> None:
        """Optional hook before the first ``scan()`` call."""

    @abstractmethod
    async def scan(self, context: ScanContext) -> list[ScanCandidate]:
        """Run one scan pass across the universe and return candidates."""

    async def on_stop(self, context: ScanContext) -> None:
        """Optional hook after the scan completes."""
