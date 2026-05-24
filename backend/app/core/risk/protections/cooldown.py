"""CooldownPeriod — Phase F2.

Blocks re-entry into the same symbol for ``stop_minutes`` after a trade
closes. Default 60 minutes — useful for mean-reversion strategies that may
otherwise flip-flop into the same name on the next bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from app.core.risk.protections.base import (
    PortfolioMetrics,
    Protection,
    ProtectionDecision,
    TradeRecord,
    add_minutes,
)


@dataclass
class CooldownPeriod(Protection):
    stop_minutes: int = 60
    """How long to lock a symbol after it closes."""

    name: str = "cooldown_period"

    def evaluate(
        self,
        *,
        symbol: str,
        now: datetime,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
    ) -> ProtectionDecision:
        for trade in recent_trades:
            if trade.symbol != symbol:
                continue
            unlock_at = add_minutes(trade.closed_at, self.stop_minutes)
            if now < unlock_at:
                return ProtectionDecision.block_symbol(
                    symbol=symbol,
                    until=unlock_at,
                    reason=(
                        f"{self.name}: last exit at {trade.closed_at.isoformat()}; "
                        f"re-entry permitted after {unlock_at.isoformat()}."
                    ),
                )
        return ProtectionDecision.allow()
