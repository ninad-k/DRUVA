"""Rate-of-change helpers for market-cycle regime detection."""

from __future__ import annotations

from decimal import Decimal

from app.strategies.base import Candle


def resample_monthly(candles: list[Candle]) -> list[Candle]:
    """Resample daily candles to monthly last-day closes. Cheap bucket-by-month."""
    if not candles:
        return []
    buckets: dict[tuple[int, int], list[Candle]] = {}
    for c in candles:
        key = (c.ts.year, c.ts.month)
        buckets.setdefault(key, []).append(c)
    out: list[Candle] = []
    for key in sorted(buckets.keys()):
        bucket = buckets[key]
        bucket.sort(key=lambda x: x.ts)
        first = bucket[0]
        last = bucket[-1]
        high = max(x.high for x in bucket)
        low = min(x.low for x in bucket)
        vol = sum((x.volume for x in bucket), Decimal("0"))
        out.append(
            Candle(
                symbol=first.symbol,
                timeframe="1M",
                ts=last.ts,
                open=first.open,
                high=high,
                low=low,
                close=last.close,
                volume=vol,
            )
        )
    return out


def roc(candles: list[Candle], months: int) -> Decimal | None:
    """Compute % change of close from ``months`` ago to today.

    ``candles`` should already be monthly (use ``resample_monthly``).
    Returns None if there are not enough bars.
    """
    if len(candles) <= months:
        return None
    start = candles[-(months + 1)].close
    end = candles[-1].close
    if start <= 0:
        return None
    return ((end - start) / start) * Decimal("100")
