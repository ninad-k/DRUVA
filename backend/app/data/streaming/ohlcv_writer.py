"""Roll incoming ticks into 1-minute OHLCV bars and persist them.

Architecture: subscribe to the StreamHub wildcard channel, accumulate ticks
into per-(symbol, exchange) buckets keyed by minute, and flush completed
bars to ``ohlcv_candles`` once we see a tick from a later minute.

Why minute-buckets instead of timers: it's correct under wall-clock skew and
has zero scheduler overhead. Strategies that need 5m / 15m / 1h aggregations
read those rollups from TimescaleDB continuous aggregates (set up via
``timescaledb_continuous_aggregate``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.streaming.hub import StreamHub
from app.data.streaming.types import Tick
from app.db.models.market_data import OhlcvCandle
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class _Bar:
    symbol: str
    exchange: str
    minute: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")

    def update(self, tick: Tick) -> None:
        if tick.last_price > self.high:
            self.high = tick.last_price
        if tick.last_price < self.low:
            self.low = tick.last_price
        self.close = tick.last_price
        if tick.last_quantity:
            self.volume += tick.last_quantity


@dataclass
class OhlcvWriter:
    hub: StreamHub
    session_factory: async_sessionmaker
    timeframe: str = "1m"
    bars: dict[tuple[str, str], _Bar] = field(default_factory=dict)
    _stop: asyncio.Event = field(default_factory=asyncio.Event)

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Subscribe to the hub wildcard and write bars forever."""
        logger.info("ohlcv_writer.started")
        async for tick in self.hub.subscribe("*"):
            if self._stop.is_set():
                break
            await self._on_tick(tick)
        await self._flush_all()
        logger.info("ohlcv_writer.stopped")

    async def _on_tick(self, tick: Tick) -> None:
        minute = tick.ts.replace(second=0, microsecond=0)
        key = (tick.symbol, tick.exchange)
        existing = self.bars.get(key)
        if existing is None:
            self.bars[key] = _Bar(
                symbol=tick.symbol,
                exchange=tick.exchange,
                minute=minute,
                open=tick.last_price,
                high=tick.last_price,
                low=tick.last_price,
                close=tick.last_price,
                volume=tick.last_quantity or Decimal("0"),
            )
            return

        if minute == existing.minute:
            existing.update(tick)
            return

        # Minute rolled over — flush the completed bar, start a new one.
        await self._flush_bar(existing)
        self.bars[key] = _Bar(
            symbol=tick.symbol,
            exchange=tick.exchange,
            minute=minute,
            open=tick.last_price,
            high=tick.last_price,
            low=tick.last_price,
            close=tick.last_price,
            volume=tick.last_quantity or Decimal("0"),
        )

    async def _flush_bar(self, bar: _Bar) -> None:
        async with self.session_factory() as session:
            stmt = insert(OhlcvCandle).values(
                ts=bar.minute.replace(tzinfo=timezone.utc),
                symbol=bar.symbol,
                exchange=bar.exchange,
                timeframe=self.timeframe,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["ts", "symbol", "exchange", "timeframe"],
                set_={
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            await session.execute(stmt)
            await session.commit()

    async def _flush_all(self) -> None:
        for bar in list(self.bars.values()):
            try:
                await self._flush_bar(bar)
            except Exception as exc:  # noqa: BLE001
                logger.warning("ohlcv_writer.flush_failed", error=str(exc))
        self.bars.clear()

    def snapshot(self) -> Mapping[tuple[str, str], _Bar]:
        """Return the in-memory bars (for /metrics or admin debugging)."""
        return dict(self.bars)
