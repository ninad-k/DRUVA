from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.notifications.telegram import TelegramNotifier
from app.db.models.order import Order


@pytest.mark.unit
@pytest.mark.asyncio
async def test_telegram_order_message_format() -> None:
    http = AsyncMock()
    notifier = TelegramNotifier("token", http)
    order = Order(
        user_id="00000000-0000-0000-0000-000000000000",
        account_id="00000000-0000-0000-0000-000000000000",
        symbol="RELIANCE",
        exchange="NSE",
        side="BUY",
        quantity="1",
        order_type="MARKET",
        product="MIS",
        status="filled",
    )
    await notifier.send_order_filled("123", order)
    call = http.post.await_args
    assert "sendMessage" in call.args[0]
    assert "Order Filled" in call.kwargs["json"]["text"]
