from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategies.base import Candle
from app.strategies.templates.momentum import MomentumStrategy


class _Ctx:
    async def place_order(self, signal):  # type: ignore[no-untyped-def]
        return ""

    async def get_position(self, symbol: str) -> Decimal:  # noqa: ARG002
        return Decimal("0")

    async def get_candles(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        return []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_momentum_strategy_emits_signal() -> None:
    s = MomentumStrategy(id="s1", account_id="a1")
    now = datetime.now(UTC)
    signal = None
    for i in range(30):
        signal = await s.on_candle(
            Candle(
                symbol="RELIANCE",
                timeframe="1m",
                ts=now + timedelta(minutes=i),
                open=Decimal("100") + i,
                high=Decimal("101") + i,
                low=Decimal("99") + i,
                close=Decimal("100") + i,
                volume=Decimal("1000"),
            ),
            _Ctx(),
        )
    assert signal is not None
