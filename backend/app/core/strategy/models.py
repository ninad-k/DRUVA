from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class BacktestMetrics:
    total_return: Decimal
    sharpe: Decimal
    sortino: Decimal
    calmar: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    trades: int


@dataclass
class BacktestTrade:
    symbol: str
    side: str
    quantity: Decimal
    entry_ts: datetime
    exit_ts: datetime
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: list[dict[str, str]]
    trades: list[BacktestTrade]
