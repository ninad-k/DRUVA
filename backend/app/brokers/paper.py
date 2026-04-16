from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

from app.brokers.base import (
    AuthSession,
    BrokerAdapter,
    BrokerCredentials,
    BrokerHealth,
    BrokerHolding,
    BrokerOrder,
    BrokerPosition,
    BrokerTrade,
    Depth,
    InstrumentMatch,
    InstrumentRecord,
    MarginDetails,
    OrderAck,
    OrderModifyRequest,
    OrderRequest,
    Quote,
)
from app.cache import keys
from app.cache.client import CacheClient
from app.utils.time import utcnow


class PaperBroker(BrokerAdapter):
    broker_id = "paper"

    def __init__(self, cache: CacheClient):
        self._cache = cache

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        return AuthSession(access_token="paper", refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        return AuthSession(access_token="paper", refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        await asyncio.sleep(random.uniform(0.05, 0.2))
        fill_price = await self._last_price(req.symbol)
        if req.order_type == "LIMIT" and req.price is not None:
            if req.side == "BUY" and fill_price > req.price:
                return OrderAck(broker_order_id=f"PAPER-{random.randint(100000, 999999)}", status="pending")
            if req.side == "SELL" and fill_price < req.price:
                return OrderAck(broker_order_id=f"PAPER-{random.randint(100000, 999999)}", status="pending")
        return OrderAck(broker_order_id=f"PAPER-{random.randint(100000, 999999)}", status="filled")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        return None

    async def get_positions(self) -> list[BrokerPosition]:
        return []

    async def get_holdings(self) -> list[BrokerHolding]:
        return []

    async def get_margin(self) -> MarginDetails:
        return MarginDetails(available_cash=Decimal("10000000"), used_margin=Decimal("0"), total=Decimal("10000000"))

    async def health(self) -> BrokerHealth:
        return BrokerHealth(is_healthy=True, latency_ms=1.0, message="paper_ok")

    async def search_symbols(self, query: str, exchange: str | None = None) -> list[InstrumentMatch]:
        return []

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        return Quote(symbol=symbol, exchange=exchange, last_price=await self._last_price(symbol), timestamp=utcnow())

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for symbol, exchange in symbols:
            out[(symbol, exchange)] = await self.get_quote(symbol, exchange)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        return Depth(bids=[], asks=[])

    async def get_history(self, symbol: str, exchange: str, interval: str, start: datetime, end: datetime):  # type: ignore[override]
        raise NotImplementedError("paper history not implemented")

    async def get_orderbook(self) -> list[BrokerOrder]:
        return []

    async def get_tradebook(self) -> list[BrokerTrade]:
        return []

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        if False:
            yield InstrumentRecord(symbol="", exchange="NSE", broker_token="", instrument_type="EQ", trading_symbol="")
        return

    async def _last_price(self, symbol: str) -> Decimal:
        cached = await self._cache.get_json(keys.price(symbol))
        if cached is None:
            return Decimal("100")
        return Decimal(str(cached.get("last_price", "100")))
