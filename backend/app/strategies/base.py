"""Base classes for all DHRUVA strategies.

Every strategy (rule-based or ML) implements :class:`Strategy`. The execution
engine calls ``on_candle`` on every new candle for every enabled strategy and
acts on the returned :class:`Signal`.

ML strategies extend :class:`~app.strategies.ml.base_ml.MLStrategy` instead,
which adds feature engineering and model loading contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

Side = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT", "SL", "SL_M"]


@dataclass(frozen=True)
class Candle:
    """OHLCV candle at a given timeframe."""

    symbol: str
    timeframe: str  # "1m", "5m", "15m", "1h", "1d"
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Signal:
    """A strategy-emitted trading signal."""

    symbol: str
    side: Side
    quantity: Decimal
    order_type: OrderType = "MARKET"
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    reason: str = ""
    confidence: float = 1.0  # 0.0 – 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fill:
    """Execution event delivered back to the strategy."""

    order_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    ts: datetime


class StrategyContext(Protocol):
    """What the engine exposes to strategies at runtime."""

    async def place_order(self, signal: Signal) -> str:
        """Submit an order derived from a Signal. Returns internal order id."""

    async def get_position(self, symbol: str) -> Decimal:
        """Current net quantity for ``symbol`` in the strategy's account."""

    async def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        """Fetch the most recent ``limit`` candles for ``symbol``/``timeframe``."""


class Strategy(ABC):
    """Abstract strategy contract — rule-based or ML."""

    # Strategy identity, set by the loader
    id: str
    account_id: str
    parameters: dict[str, Any]

    def __init__(self, *, id: str, account_id: str, parameters: dict[str, Any] | None = None):
        self.id = id
        self.account_id = account_id
        self.parameters = parameters or {}

    # ---- Lifecycle -------------------------------------------------------
    async def on_start(self, context: StrategyContext) -> None:
        """Called once when the strategy is enabled."""

    async def on_stop(self, context: StrategyContext) -> None:
        """Called once when the strategy is disabled or the app shuts down."""

    # ---- Events ----------------------------------------------------------
    @abstractmethod
    async def on_candle(
        self,
        candle: Candle,
        context: StrategyContext,
    ) -> Signal | None:
        """Called on every new candle. Return a :class:`Signal` to act, or ``None``."""

    async def on_fill(self, fill: Fill, context: StrategyContext) -> None:
        """Optional hook: called after one of this strategy's orders fills."""
