"""Tick-to-OHLCV aggregator for intraday scalping strategies.

Aggregates raw price ticks into OHLCV candles at configurable intervals:
  1s, 5s, 15s, 30s, 1m

Also computes real-time VWAP (volume-weighted average price) — reset at market open (9:15 IST).
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

# IST = UTC+5:30
_IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60
_MARKET_OPEN_IST = time(9, 15, 0)


def _to_ist(dt: datetime) -> datetime:
    """Convert a UTC-aware datetime to IST (naive) for time comparisons."""
    utc_ts = dt.timestamp()
    ist_ts = utc_ts + _IST_OFFSET_SECONDS
    return datetime.utcfromtimestamp(ist_ts)


def _candle_bucket(ts: datetime, interval_seconds: int) -> datetime:
    """Return the candle-open timestamp (UTC) for the bucket that ts falls into."""
    epoch = int(ts.timestamp())
    bucket_epoch = (epoch // interval_seconds) * interval_seconds
    return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)


@dataclass
class Tick:
    """A single price tick from a market feed."""

    symbol: str
    price: Decimal
    volume: int
    timestamp: datetime  # UTC-aware


@dataclass
class AggregatedCandle:
    """OHLCV candle produced by the aggregator."""

    symbol: str
    interval_seconds: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal
    ts: datetime  # candle open time (UTC)


@dataclass
class _CandleAccumulator:
    """Mutable accumulator for in-progress candle data."""

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    pv_sum: Decimal  # sum(price * volume) for candle-level VWAP
    ts: datetime    # candle open time (UTC)

    def update(self, price: Decimal, volume: int) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += volume
        self.pv_sum += price * volume

    @property
    def candle_vwap(self) -> Decimal:
        if self.volume == 0:
            return self.close
        return self.pv_sum / self.volume


class TickAggregator:
    """Aggregates raw ticks into OHLCV candles at multiple configurable intervals.

    Thread-safe via asyncio.Lock — safe to call from concurrent coroutines but
    must be used within a single event loop.

    Usage::

        aggregator = TickAggregator(symbol="NSE:NIFTY FUT", intervals=[5, 30, 60])
        completed = await aggregator.ingest(tick)
        for candle in completed:
            ...  # publish to strategy engine
    """

    def __init__(
        self,
        symbol: str,
        intervals: list[int] | None = None,
    ) -> None:
        self.symbol = symbol
        self.intervals: list[int] = intervals if intervals is not None else [5, 30, 60]

        # Tick ring-buffer — 10 000 ticks max to bound memory
        self._tick_buffer: deque[Tick] = deque(maxlen=10_000)

        # Per-interval in-progress candle accumulators
        self._accumulators: dict[int, _CandleAccumulator | None] = {
            iv: None for iv in self.intervals
        }

        # Session-level VWAP accumulators (reset at 9:15 IST)
        self._vwap_pv: Decimal = Decimal(0)  # sum(price * volume)
        self._vwap_vol: int = 0              # sum(volume)

        self._lock: asyncio.Lock = asyncio.Lock()

        logger.info(
            "tick_aggregator.init",
            symbol=symbol,
            intervals=self.intervals,
        )

    # ---------------------------------------------------------------------- public

    async def ingest(self, tick: Tick) -> list[AggregatedCandle]:
        """Accept a new tick and return any candles that completed as a result.

        A candle is considered *completed* when a new tick falls into a
        different time bucket than the candle that was open.
        """
        if tick.symbol != self.symbol:
            logger.warning(
                "tick_aggregator.symbol_mismatch",
                expected=self.symbol,
                got=tick.symbol,
            )
            return []

        async with self._lock:
            self._tick_buffer.append(tick)
            self._update_session_vwap(tick)

            completed: list[AggregatedCandle] = []
            for interval in self.intervals:
                bucket = _candle_bucket(tick.timestamp, interval)
                acc = self._accumulators[interval]

                if acc is None:
                    # First tick ever — open a new candle
                    self._accumulators[interval] = _CandleAccumulator(
                        open=tick.price,
                        high=tick.price,
                        low=tick.price,
                        close=tick.price,
                        volume=tick.volume,
                        pv_sum=tick.price * tick.volume,
                        ts=bucket,
                    )
                elif bucket > acc.ts:
                    # Tick crossed a bucket boundary — close old, open new
                    closed = self._close_candle(interval)
                    if closed is not None:
                        completed.append(closed)
                    self._accumulators[interval] = _CandleAccumulator(
                        open=tick.price,
                        high=tick.price,
                        low=tick.price,
                        close=tick.price,
                        volume=tick.volume,
                        pv_sum=tick.price * tick.volume,
                        ts=bucket,
                    )
                else:
                    # Same bucket — update running candle
                    acc.update(tick.price, tick.volume)

            return completed

    def current_vwap(self, symbol: str) -> Decimal:
        """Return the running session VWAP (since 9:15 IST) for *symbol*.

        Returns the last close price if no volume has been accumulated.
        """
        if symbol != self.symbol:
            raise ValueError(f"Symbol mismatch: expected {self.symbol}, got {symbol}")
        if self._vwap_vol == 0:
            # No ticks yet — return last observed price or zero
            if self._tick_buffer:
                return self._tick_buffer[-1].price
            return Decimal(0)
        return self._vwap_pv / self._vwap_vol

    def vwap_deviation_pct(self, current_price: Decimal) -> float:
        """Return (price - vwap) / vwap * 100.

        Positive = price is above VWAP, negative = price is below VWAP.
        """
        vwap = current_vwap = self.current_vwap(self.symbol)
        if vwap == 0:
            return 0.0
        try:
            deviation = float((current_price - current_vwap) / current_vwap * 100)
        except (InvalidOperation, ZeroDivisionError):
            deviation = 0.0
        return deviation

    def reset_daily(self) -> None:
        """Reset VWAP accumulators and in-progress candles at market open (9:15 IST).

        Call this at exactly 09:15 IST every weekday from a scheduler.
        """
        self._vwap_pv = Decimal(0)
        self._vwap_vol = 0
        for interval in self.intervals:
            self._accumulators[interval] = None
        logger.info("tick_aggregator.daily_reset", symbol=self.symbol)

    def _close_candle(self, interval: int) -> AggregatedCandle | None:
        """Finalise and return the completed candle for *interval*.

        Returns None if there is no open candle for that interval.
        """
        acc = self._accumulators.get(interval)
        if acc is None:
            return None

        candle = AggregatedCandle(
            symbol=self.symbol,
            interval_seconds=interval,
            open=acc.open,
            high=acc.high,
            low=acc.low,
            close=acc.close,
            volume=acc.volume,
            vwap=acc.candle_vwap,
            ts=acc.ts,
        )
        logger.debug(
            "tick_aggregator.candle_closed",
            symbol=self.symbol,
            interval=interval,
            ts=acc.ts.isoformat(),
            open=str(acc.open),
            close=str(acc.close),
            volume=acc.volume,
        )
        return candle

    # ---------------------------------------------------------------------- private

    def _update_session_vwap(self, tick: Tick) -> None:
        """Update running VWAP state; called inside the lock from ingest()."""
        self._vwap_pv += tick.price * tick.volume
        self._vwap_vol += tick.volume
