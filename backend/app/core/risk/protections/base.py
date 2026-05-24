"""Base types for the protections framework."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

ProtectionScope = Literal["symbol", "global"]


@dataclass(frozen=True)
class TradeRecord:
    """Minimal closed-trade record consumed by every protection.

    All amounts are in the issuer's base currency (INR for DRUVA). ``pnl_pct``
    is the realised P&L as a fraction of the trade's notional value at entry
    (``-0.02 == -2% loss``). ``hit_stoploss`` is ``True`` when the trade
    exited via the stop-loss leg.
    """

    symbol: str
    closed_at: datetime
    pnl_pct: float
    hit_stoploss: bool = False
    notional_inr: float = 0.0
    strategy_id: str | None = None


@dataclass(frozen=True)
class ProtectionDecision:
    """Result returned by a single protection."""

    blocked: bool
    scope: ProtectionScope
    symbol: str | None
    until: datetime | None
    reason: str
    """One-line human-readable explanation, surfaced in the UI + notifications."""

    @classmethod
    def allow(cls) -> "ProtectionDecision":
        return cls(blocked=False, scope="symbol", symbol=None, until=None, reason="")

    @classmethod
    def block_symbol(cls, *, symbol: str, until: datetime, reason: str) -> "ProtectionDecision":
        return cls(blocked=True, scope="symbol", symbol=symbol, until=until, reason=reason)

    @classmethod
    def block_global(cls, *, until: datetime, reason: str) -> "ProtectionDecision":
        return cls(blocked=True, scope="global", symbol=None, until=until, reason=reason)


class Protection(ABC):
    """Abstract protection policy."""

    name: str = "protection"

    @abstractmethod
    def evaluate(
        self,
        *,
        symbol: str,
        now: datetime,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: "PortfolioMetrics",
    ) -> ProtectionDecision:
        """Decide whether the named symbol (or the whole book) should be blocked."""


@dataclass
class PortfolioMetrics:
    """Snapshot consumed by drawdown / equity protections."""

    total_value: float
    """Current total portfolio value in INR."""

    peak_value: float
    """All-time peak portfolio value in INR (running max)."""

    daily_pnl_pct: float = 0.0
    open_positions: int = 0
    metadata: dict[str, float] = field(default_factory=dict)


def now_utc() -> datetime:
    """Single utility so all protections share the same clock."""
    return datetime.now(timezone.utc)


def add_minutes(ts: datetime, minutes: int) -> datetime:
    return ts + timedelta(minutes=int(minutes))
