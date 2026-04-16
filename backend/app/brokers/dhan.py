from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from app.brokers.base import *  # noqa: F403


class DhanAdapter(BrokerAdapter):
    broker_id = "dhan"

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def refresh_token(self) -> AuthSession:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def place_order(self, req: OrderRequest) -> OrderAck:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def cancel_order(self, broker_order_id: str) -> None:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_positions(self) -> list[BrokerPosition]:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_holdings(self) -> list[BrokerHolding]:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_margin(self) -> MarginDetails:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def health(self) -> BrokerHealth:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def search_symbols(self, query: str, exchange: str | None = None) -> list[InstrumentMatch]:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_quote(self, symbol: str, exchange: str) -> Quote:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_history(self, symbol: str, exchange: str, interval: str, start: datetime, end: datetime):  # type: ignore[override] # noqa: ARG002
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        raise NotImplementedError("TODO: dhan - will be filled in Day 10")
