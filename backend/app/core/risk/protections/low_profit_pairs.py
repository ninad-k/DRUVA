"""LowProfitPairs — Phase F2.

Drops a symbol from the tradable universe if its rolling-window expectancy
is below ``min_profit_pct``. Particularly useful for strategies that scan
hundreds of names — the worst-performing tail is auto-paused so capital
flows to the strategies that actually compound.
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
class LowProfitPairs(Protection):
    lookback_minutes: int = 7 * 24 * 60     # 1 week
    min_profit_pct: float = 0.0             # require non-negative expectancy
    required_trades: int = 3
    stop_minutes: int = 24 * 60

    name: str = "low_profit_pairs"

    def evaluate(
        self,
        *,
        symbol: str,
        now: datetime,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
    ) -> ProtectionDecision:
        window_start = now - timedelta(minutes=self.lookback_minutes)
        symbol_trades = [
            t for t in recent_trades
            if t.symbol == symbol and t.closed_at >= window_start
        ]
        if len(symbol_trades) < self.required_trades:
            return ProtectionDecision.allow()
        mean_pnl_pct = sum(t.pnl_pct for t in symbol_trades) / len(symbol_trades) * 100.0
        if mean_pnl_pct < self.min_profit_pct:
            until = add_minutes(now, self.stop_minutes)
            return ProtectionDecision.block_symbol(
                symbol=symbol,
                until=until,
                reason=(
                    f"{self.name}: mean P&L {mean_pnl_pct:.2f}% over "
                    f"{len(symbol_trades)} trades < {self.min_profit_pct:.2f}%; "
                    f"paused until {until.isoformat()}."
                ),
            )
        return ProtectionDecision.allow()
