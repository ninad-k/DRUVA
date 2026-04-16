"""Read access to OHLCV candles stored in the TimescaleDB hypertable.

Strategies and backtests fetch candles via this repository so the storage
choice (TimescaleDB hypertable today, possibly something else later) stays
hidden behind a stable interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.market_data import OhlcvCandle
from app.strategies.base import Candle


@dataclass
class OhlcvRepository:
    """Async repository over the ``ohlcv_candles`` hypertable."""

    session: AsyncSession

    async def latest(
        self,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        limit: int,
    ) -> list[Candle]:
        """Return the most recent ``limit`` candles for the given symbol/timeframe.

        Returned in ascending timestamp order so consumers can use ``[-1]`` for
        the newest candle.
        """
        rows = (
            await self.session.execute(
                select(OhlcvCandle)
                .where(
                    OhlcvCandle.symbol == symbol,
                    OhlcvCandle.exchange == exchange,
                    OhlcvCandle.timeframe == timeframe,
                )
                .order_by(OhlcvCandle.ts.desc())
                .limit(limit)
            )
        ).scalars().all()
        rows.reverse()
        return [
            Candle(
                symbol=row.symbol,
                timeframe=row.timeframe,
                ts=row.ts,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        ]

    async def range(
        self,
        *,
        symbol: str,
        exchange: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Return candles in ``[start, end]`` inclusive, ascending."""
        rows = (
            await self.session.execute(
                select(OhlcvCandle)
                .where(
                    OhlcvCandle.symbol == symbol,
                    OhlcvCandle.exchange == exchange,
                    OhlcvCandle.timeframe == timeframe,
                    OhlcvCandle.ts >= start,
                    OhlcvCandle.ts <= end,
                )
                .order_by(OhlcvCandle.ts.asc())
            )
        ).scalars().all()
        return [
            Candle(
                symbol=row.symbol,
                timeframe=row.timeframe,
                ts=row.ts,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in rows
        ]
