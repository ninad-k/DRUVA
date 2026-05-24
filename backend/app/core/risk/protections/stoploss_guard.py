"""StoplossGuard — Phase F2.

If the strategy has hit its stop-loss too many times within a sliding window
(globally or per-symbol), block further entries until the window ages out.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from app.core.risk.protections.base import (
    PortfolioMetrics,
    Protection,
    ProtectionDecision,
    TradeRecord,
    add_minutes,
)


@dataclass
class StoplossGuard(Protection):
    lookback_minutes: int = 1440        # 24 hours
    trade_limit: int = 4
    stop_minutes: int = 60
    only_per_symbol: bool = False

    name: str = "stoploss_guard"

    def evaluate(
        self,
        *,
        symbol: str,
        now: datetime,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
    ) -> ProtectionDecision:
        window_start = now - timedelta(minutes=self.lookback_minutes)
        relevant = [
            t for t in recent_trades
            if t.closed_at >= window_start and t.hit_stoploss
            and (not self.only_per_symbol or t.symbol == symbol)
        ]
        if len(relevant) >= self.trade_limit:
            until = add_minutes(now, self.stop_minutes)
            reason = (
                f"{self.name}: {len(relevant)} stop-loss exits in the last "
                f"{self.lookback_minutes} min "
                f"(limit {self.trade_limit}); paused until {until.isoformat()}."
            )
            if self.only_per_symbol:
                return ProtectionDecision.block_symbol(symbol=symbol, until=until, reason=reason)
            return ProtectionDecision.block_global(until=until, reason=reason)
        return ProtectionDecision.allow()
