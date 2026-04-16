"""LatencyRecordingAdapter must:
1. Record both success and failure rows.
2. Properly forward an *async generator* method (download_master_contract)
   without breaking iteration. The previous wrapper double-wrapped it as a
   coroutine, which crashed the master-contract sync.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.brokers.base import (
    AuthSession,
    BrokerCredentials,
    InstrumentRecord,
    OrderAck,
    OrderRequest,
)
from app.brokers.latency_wrapper import LatencyRecorder, LatencyRecordingAdapter


class _FakeAdapter:
    broker_id = "fake"

    def __init__(self, fail_place: bool = False, records: int = 3):
        self.fail_place = fail_place
        self._records = records

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        return AuthSession(access_token="t", refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        return AuthSession(access_token="t", refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        if self.fail_place:
            raise RuntimeError("boom")
        return OrderAck(broker_order_id="X", status="filled")

    async def modify_order(self, *args, **kwargs):
        return OrderAck(broker_order_id="X", status="modified")

    async def cancel_order(self, *args, **kwargs):
        return None

    async def get_positions(self):
        return []

    async def get_holdings(self):
        return []

    async def get_margin(self):
        return MagicMock(available_cash=Decimal("0"), used_margin=Decimal("0"), total=Decimal("0"))

    async def health(self):
        return MagicMock(is_healthy=True, latency_ms=1.0, message="ok")

    async def search_symbols(self, q, exchange=None):
        return []

    async def get_quote(self, symbol, exchange):
        return MagicMock()

    async def get_quotes(self, symbols):
        return {}

    async def get_depth(self, symbol, exchange):
        return MagicMock()

    async def get_history(self, *args, **kwargs):
        return []

    async def get_orderbook(self):
        return []

    async def get_tradebook(self):
        return []

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        for i in range(self._records):
            yield InstrumentRecord(
                symbol=f"SYM{i}",
                exchange="NSE",
                broker_token=f"T{i}",
                instrument_type="EQ",
                trading_symbol=f"SYM{i}",
            )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_records_success() -> None:
    recorder = MagicMock(spec=LatencyRecorder)
    recorder.record = AsyncMock()
    inner = _FakeAdapter()
    wrapper = LatencyRecordingAdapter(inner, recorder)

    ack = await wrapper.place_order(
        OrderRequest(
            symbol="A",
            exchange="NSE",
            side="BUY",
            quantity=Decimal("1"),
            order_type="MARKET",
            product="MIS",
        )
    )
    assert ack.status == "filled"
    recorder.record.assert_awaited_once()
    args = recorder.record.await_args.kwargs
    assert args["operation"] == "place_order"
    assert args["status"] == "success"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_records_failure_and_reraises() -> None:
    recorder = MagicMock(spec=LatencyRecorder)
    recorder.record = AsyncMock()
    inner = _FakeAdapter(fail_place=True)
    wrapper = LatencyRecordingAdapter(inner, recorder)

    with pytest.raises(RuntimeError, match="boom"):
        await wrapper.place_order(
            OrderRequest(
                symbol="A",
                exchange="NSE",
                side="BUY",
                quantity=Decimal("1"),
                order_type="MARKET",
                product="MIS",
            )
        )
    recorder.record.assert_awaited_once()
    assert recorder.record.await_args.kwargs["status"] == "failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_generator_method_passes_through() -> None:
    """download_master_contract must remain iterable; the wrapper drives it
    and records once when the iterator exhausts."""
    recorder = MagicMock(spec=LatencyRecorder)
    recorder.record = AsyncMock()
    inner = _FakeAdapter(records=4)
    wrapper = LatencyRecordingAdapter(inner, recorder)

    collected = [r async for r in wrapper.download_master_contract()]
    assert len(collected) == 4
    recorder.record.assert_awaited_once()
    assert recorder.record.await_args.kwargs["operation"] == "download_master_contract"
    assert recorder.record.await_args.kwargs["status"] == "success"
