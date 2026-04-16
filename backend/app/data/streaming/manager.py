"""Streaming subscription manager.

Owns the broker WebSocket connections for each active account and pushes
incoming ticks into the central StreamHub. Subscriptions are computed from
the union of:
- symbols held in active positions for paper/live accounts
- symbols referenced by enabled strategies' parameters
- symbols any client explicitly subscribed to via the WS API

If a broker adapter doesn't expose a streaming method, that broker is
silently skipped — the rest of the bus keeps working.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.brokers.factory import BrokerFactory
from app.data.streaming.hub import StreamHub
from app.data.streaming.types import Tick
from app.db.models.account import Account
from app.db.models.position import Position
from app.db.models.strategy import Strategy
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StreamingManager:
    hub: StreamHub
    factory: BrokerFactory
    session_factory: async_sessionmaker
    poll_seconds: int = 30
    _stop: asyncio.Event = field(default_factory=asyncio.Event)
    _broker_tasks: dict[str, asyncio.Task] = field(default_factory=dict)

    async def stop(self) -> None:
        self._stop.set()
        for task in list(self._broker_tasks.values()):
            task.cancel()
        await asyncio.gather(*self._broker_tasks.values(), return_exceptions=True)

    async def run(self) -> None:
        """Top-level supervisor: every ``poll_seconds`` recompute desired
        subscriptions and (re)start broker streams as needed."""
        logger.info("streaming_manager.started")
        while not self._stop.is_set():
            try:
                await self._reconcile()
            except Exception as exc:  # noqa: BLE001
                logger.warning("streaming_manager.reconcile_failed", error=str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("streaming_manager.stopped")

    async def _reconcile(self) -> None:
        async with self.session_factory() as session:
            accounts = (
                await session.execute(select(Account).where(Account.is_active.is_(True)))
            ).scalars().all()
            symbols_for: dict[str, set[tuple[str, str]]] = {}
            for account in accounts:
                positions = (
                    await session.execute(
                        select(Position).where(Position.account_id == account.id)
                    )
                ).scalars().all()
                strategies = (
                    await session.execute(
                        select(Strategy).where(
                            Strategy.account_id == account.id,
                            Strategy.is_enabled.is_(True),
                            Strategy.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
                bucket = symbols_for.setdefault(account.broker_id, set())
                for p in positions:
                    bucket.add((p.symbol, str(p.exchange)))
                for s in strategies:
                    for sym in (s.parameters or {}).get("symbols", []) or []:
                        bucket.add((str(sym), str((s.parameters or {}).get("exchange", "NSE"))))

            # Start one task per broker; if the broker adapter lacks streaming
            # support we just skip it.
            for account in accounts:
                if account.broker_id in self._broker_tasks:
                    if self._broker_tasks[account.broker_id].done():
                        del self._broker_tasks[account.broker_id]
                    else:
                        continue
                if not symbols_for.get(account.broker_id):
                    continue
                self._broker_tasks[account.broker_id] = asyncio.create_task(
                    self._stream_one(account, symbols_for[account.broker_id]),
                    name=f"stream:{account.broker_id}",
                )

    async def _stream_one(self, account: Account, symbols: set[tuple[str, str]]) -> None:
        broker = await self.factory.create(account)
        stream_method: Any = getattr(broker, "stream_ticks", None)
        if stream_method is None:
            logger.info(
                "streaming_manager.broker_not_streamable",
                broker_id=account.broker_id,
            )
            return
        try:
            async for tick in stream_method(list(symbols)):
                await self.hub.publish(tick)
                if self._stop.is_set():
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "streaming_manager.broker_stream_failed",
                broker_id=account.broker_id,
                error=str(exc),
            )


def fake_tick(symbol: str, exchange: str, price: str) -> Tick:
    """Used by tests and dev environments without a live broker. The
    StreamingManager itself never calls this."""
    from datetime import datetime, timezone
    from decimal import Decimal

    return Tick(
        symbol=symbol,
        exchange=exchange,
        last_price=Decimal(price),
        last_quantity=Decimal("1"),
        ts=datetime.now(timezone.utc),
    )
