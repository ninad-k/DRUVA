"""MaxDrawdownProtection — Phase F2.

Halts new entries when the portfolio's peak-to-trough drawdown exceeds
``max_drawdown_pct``. Stays in effect for ``stop_minutes`` after the breach,
giving the market time to recover and the operator time to investigate.
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
class MaxDrawdownProtection(Protection):
    max_drawdown_pct: float = 15.0     # %
    stop_minutes: int = 24 * 60         # 24 hours

    name: str = "max_drawdown_protection"

    def evaluate(
        self,
        *,
        symbol: str,
        now: datetime,
        recent_trades: Iterable[TradeRecord],
        portfolio_state: PortfolioMetrics,
    ) -> ProtectionDecision:
        peak = max(portfolio_state.peak_value, portfolio_state.total_value, 1e-9)
        drawdown_pct = (peak - portfolio_state.total_value) / peak * 100.0
        if drawdown_pct >= self.max_drawdown_pct:
            until = add_minutes(now, self.stop_minutes)
            return ProtectionDecision.block_global(
                until=until,
                reason=(
                    f"{self.name}: drawdown {drawdown_pct:.2f}% "
                    f"≥ limit {self.max_drawdown_pct:.2f}%; "
                    f"new entries paused until {until.isoformat()}."
                ),
            )
        return ProtectionDecision.allow()
