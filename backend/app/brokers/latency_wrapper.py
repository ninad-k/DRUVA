"""Decorator that wraps every BrokerAdapter method to record per-call latency.

Important subtlety: ``download_master_contract`` returns an *async generator*
(not a coroutine). Calling ``await broker.download_master_contract()`` would
TypeError because the function returns the generator, not an awaitable.

We special-case it here: the wrapper drives the inner generator itself,
yielding each record back to the caller while measuring total wall time. The
rest of the methods are plain async functions handled by ``_run``.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
from app.db.models.latency import LatencySample
from app.strategies.base import Candle


class LatencyRecorder:
    """Persists a row in the ``latency_samples`` hypertable per call.

    Uses its own session per write so it doesn't interfere with caller txns.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def record(
        self,
        *,
        broker_id: str,
        operation: str,
        latency_ms: float,
        status: str,
        account_id: UUID | None = None,
    ) -> None:
        async with self._session_factory() as session:
            session.add(
                LatencySample(
                    ts=datetime.now(UTC),
                    broker_id=broker_id,
                    operation=operation,
                    account_id=account_id,
                    latency_ms=Decimal(str(round(latency_ms, 4))),
                    status=status,
                )
            )
            await session.commit()


class LatencyRecordingAdapter(BrokerAdapter):
    """Transparent decorator: implements every BrokerAdapter method by timing
    a delegate call and recording the result.
    """

    def __init__(self, inner: BrokerAdapter, recorder: LatencyRecorder):
        self._inner = inner
        self._recorder = recorder
        self.broker_id = inner.broker_id

    async def _run(self, operation: str, fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            await self._recorder.record(
                broker_id=self.broker_id,
                operation=operation,
                latency_ms=(time.perf_counter() - started) * 1000,
                status="failed",
            )
            raise
        await self._recorder.record(
            broker_id=self.broker_id,
            operation=operation,
            latency_ms=(time.perf_counter() - started) * 1000,
            status="success",
        )
        return result

    # ---- Coroutine methods ------------------------------------------------

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        return await self._run("authenticate", self._inner.authenticate, creds)

    async def refresh_token(self) -> AuthSession:
        return await self._run("refresh_token", self._inner.refresh_token)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        return await self._run("place_order", self._inner.place_order, req)

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        return await self._run("modify_order", self._inner.modify_order, broker_order_id, req)

    async def cancel_order(self, broker_order_id: str) -> None:
        return await self._run("cancel_order", self._inner.cancel_order, broker_order_id)

    async def get_positions(self) -> list[BrokerPosition]:
        return await self._run("get_positions", self._inner.get_positions)

    async def get_holdings(self) -> list[BrokerHolding]:
        return await self._run("get_holdings", self._inner.get_holdings)

    async def get_margin(self) -> MarginDetails:
        return await self._run("get_margin", self._inner.get_margin)

    async def health(self) -> BrokerHealth:
        return await self._run("health", self._inner.health)

    async def search_symbols(
        self, query: str, exchange: str | None = None
    ) -> list[InstrumentMatch]:
        return await self._run("search_symbols", self._inner.search_symbols, query, exchange)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        return await self._run("get_quote", self._inner.get_quote, symbol, exchange)

    async def get_quotes(
        self, symbols: list[tuple[str, str]]
    ) -> dict[tuple[str, str], Quote]:
        return await self._run("get_quotes", self._inner.get_quotes, symbols)

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        return await self._run("get_depth", self._inner.get_depth, symbol, exchange)

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,  # type: ignore[override]
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        return await self._run(
            "get_history", self._inner.get_history, symbol, exchange, interval, start, end
        )

    async def get_orderbook(self) -> list[BrokerOrder]:
        return await self._run("get_orderbook", self._inner.get_orderbook)

    async def get_tradebook(self) -> list[BrokerTrade]:
        return await self._run("get_tradebook", self._inner.get_tradebook)

    # ---- Async generator method (special-cased) ---------------------------

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        """Drive the inner generator and record total wall time.

        Critically, this is an *async generator*: the caller writes
        ``async for record in adapter.download_master_contract():`` (NO ``await``
        before the call). The wrapper yields records as they arrive and
        records latency once when the iterator exhausts (or fails).
        """
        started = time.perf_counter()
        try:
            inner_iter = self._inner.download_master_contract()
            async for record in inner_iter:
                yield record
        except Exception:
            await self._recorder.record(
                broker_id=self.broker_id,
                operation="download_master_contract",
                latency_ms=(time.perf_counter() - started) * 1000,
                status="failed",
            )
            raise
        await self._recorder.record(
            broker_id=self.broker_id,
            operation="download_master_contract",
            latency_ms=(time.perf_counter() - started) * 1000,
            status="success",
        )
