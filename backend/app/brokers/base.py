"""Abstract broker adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from app.strategies.base import Candle


@dataclass(frozen=True)
class BrokerCredentials:
    api_key: str
    api_secret: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuthSession:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    exchange: str
    side: str
    quantity: Decimal
    order_type: str
    product: str
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    tag: str | None = None


@dataclass(frozen=True)
class OrderAck:
    broker_order_id: str
    status: str
    message: str = ""


@dataclass(frozen=True)
class OrderModifyRequest:
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: str | None = None


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    exchange: str
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal
    pnl: Decimal
    product: str


@dataclass(frozen=True)
class BrokerHolding:
    symbol: str
    exchange: str
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal


@dataclass(frozen=True)
class MarginDetails:
    available_cash: Decimal
    used_margin: Decimal
    total: Decimal


@dataclass(frozen=True)
class BrokerHealth:
    is_healthy: bool
    latency_ms: float
    message: str = ""


@dataclass(frozen=True)
class InstrumentMatch:
    symbol: str
    exchange: str
    trading_symbol: str
    instrument_type: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    exchange: str
    last_price: Decimal
    timestamp: datetime


@dataclass(frozen=True)
class DepthLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class Depth:
    bids: list[DepthLevel]
    asks: list[DepthLevel]


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    symbol: str
    status: str
    quantity: Decimal
    price: Decimal | None


@dataclass(frozen=True)
class BrokerTrade:
    broker_trade_id: str
    broker_order_id: str
    symbol: str
    quantity: Decimal
    price: Decimal
    traded_at: datetime


@dataclass(frozen=True)
class InstrumentRecord:
    symbol: str
    exchange: str
    broker_token: str
    instrument_type: str
    trading_symbol: str
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    expiry: date | None = None
    strike: Decimal | None = None
    isin: str | None = None
    exchange_token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BrokerAdapter(ABC):
    broker_id: str

    @abstractmethod
    async def authenticate(self, creds: BrokerCredentials) -> AuthSession: ...

    @abstractmethod
    async def refresh_token(self) -> AuthSession: ...

    @abstractmethod
    async def place_order(self, req: OrderRequest) -> OrderAck: ...

    @abstractmethod
    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> None: ...

    @abstractmethod
    async def get_positions(self) -> list[BrokerPosition]: ...

    @abstractmethod
    async def get_holdings(self) -> list[BrokerHolding]: ...

    @abstractmethod
    async def get_margin(self) -> MarginDetails: ...

    @abstractmethod
    async def health(self) -> BrokerHealth: ...

    @abstractmethod
    async def search_symbols(self, query: str, exchange: str | None = None) -> list[InstrumentMatch]: ...

    @abstractmethod
    async def get_quote(self, symbol: str, exchange: str) -> Quote: ...

    @abstractmethod
    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]: ...

    @abstractmethod
    async def get_depth(self, symbol: str, exchange: str) -> Depth: ...

    @abstractmethod
    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: Literal["1m", "5m", "15m", "1h", "1d"],
        start: datetime,
        end: datetime,
    ) -> list[Candle]: ...

    @abstractmethod
    async def get_orderbook(self) -> list[BrokerOrder]: ...

    @abstractmethod
    async def get_tradebook(self) -> list[BrokerTrade]: ...

    @abstractmethod
    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]: ...
