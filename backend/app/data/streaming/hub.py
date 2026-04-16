"""In-process pub/sub for market-data ticks.

Multiple consumers (OHLCV writer, WebSocket-out router, strategy loop) need
the same tick stream. We keep a per-channel set of asyncio Queues and fan a
publish out to all of them. Subscribers iterate ``async for`` over their
queue and unsubscribe when done.

Channels are simply strings — convention is ``{exchange}:{symbol}`` so a
strategy can subscribe to a precise instrument. ``*`` is reserved for "all
ticks" (used by the OHLCV writer).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from app.data.streaming.types import Tick
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_WILDCARD = "*"


class StreamHub:
    def __init__(self, max_queue: int = 1000):
        self._max_queue = max_queue
        self._channels: dict[str, set[asyncio.Queue[Tick]]] = defaultdict(set)

    async def publish(self, tick: Tick) -> None:
        """Fan ``tick`` out to all matching subscribers (specific channel + wildcard)."""
        channel = f"{tick.exchange}:{tick.symbol}"
        for ch in (channel, _WILDCARD):
            for queue in list(self._channels.get(ch, ())):
                try:
                    queue.put_nowait(tick)
                except asyncio.QueueFull:
                    # Drop the slowest subscriber's oldest item rather than
                    # block the publisher. Better stale-tick than blocked bus.
                    try:
                        queue.get_nowait()
                        queue.put_nowait(tick)
                    except Exception:  # noqa: BLE001
                        logger.warning("stream_hub.drop", channel=ch)

    async def subscribe(self, channel: str) -> AsyncIterator[Tick]:
        """``async for tick in hub.subscribe('NSE:RELIANCE'): ...``

        Yields ticks until the consumer breaks out. Cleans up the queue when
        the iterator is closed.
        """
        queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=self._max_queue)
        self._channels[channel].add(queue)
        try:
            while True:
                tick = await queue.get()
                yield tick
        finally:
            self._channels[channel].discard(queue)
            if not self._channels[channel]:
                del self._channels[channel]

    @property
    def channel_count(self) -> int:
        return len(self._channels)
