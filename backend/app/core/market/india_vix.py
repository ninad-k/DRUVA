"""India VIX fetcher — NSE public endpoint, no authentication required.

VIX thresholds:
  < 13   → Very low fear  → Euphoria/Bull regime boost
  13–17  → Normal         → no modifier
  17–22  → Elevated fear  → Neutral bias
  22–28  → High fear      → Bear bias
  > 28   → Extreme fear   → Crash bias
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

NSE_INDICES_URL = "https://www.nseindia.com/api/allIndices"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "X-Requested-With": "XMLHttpRequest",
}

# Module-level cache: {"reading": VixReading, "fetched_at": datetime}
_cache: dict[str, Any] = {}
_CACHE_TTL = timedelta(minutes=5)

# Fallback value when NSE is unreachable
_FALLBACK_VIX = 16.0


@dataclass(frozen=True)
class VixReading:
    """A single India VIX data point."""

    value: float
    change_pct: float
    fetched_at: datetime


def vix_to_regime_modifier(vix: float) -> int:
    """Map an India VIX level to a regime modifier integer.

    Returns:
        +2  (very low fear  — Bull/Euphoria boost)
        +1  (low fear)
         0  (normal — no modifier)
        -1  (elevated fear — Neutral bias)
        -2  (extreme fear  — Crash bias)
    """
    if vix < 13.0:
        return 2
    if vix < 17.0:
        return 0
    if vix < 22.0:
        return -1
    if vix < 28.0:
        return -2
    return -2


async def fetch_india_vix(client: httpx.AsyncClient) -> VixReading:
    """Fetch live India VIX from the NSE public indices endpoint.

    NSE returns a JSON array of index objects; India VIX has
    ``indexSymbol == "INDIA VIX"``.

    Raises:
        httpx.HTTPError: on network failure
        ValueError: if VIX record is not found in the response
    """
    resp = await client.get(
        NSE_INDICES_URL,
        headers=NSE_HEADERS,
        timeout=15.0,
    )
    resp.raise_for_status()
    payload = resp.json()

    records: list[dict[str, Any]] = payload.get("data", [])
    for rec in records:
        if rec.get("indexSymbol", "").upper() == "INDIA VIX":
            value = float(rec.get("last", 0))
            change_pct = float(rec.get("percentChange", 0))
            reading = VixReading(value=value, change_pct=change_pct, fetched_at=utcnow())
            logger.info(
                "india_vix.fetched",
                vix=value,
                change_pct=change_pct,
            )
            return reading

    raise ValueError("India VIX record not found in NSE response")


def _is_cache_valid() -> bool:
    """Return True if the module-level cache holds a fresh reading."""
    cached_at: datetime | None = _cache.get("fetched_at")
    if cached_at is None:
        return False
    return (utcnow() - cached_at) < _CACHE_TTL


def _store_in_cache(reading: VixReading) -> None:
    """Persist a reading in the module-level cache."""
    _cache["reading"] = reading
    _cache["fetched_at"] = reading.fetched_at


async def get_vix_with_fallback(client: httpx.AsyncClient) -> VixReading:
    """Return a VixReading, using cache or falling back gracefully on error.

    Cache TTL is 5 minutes. On fetch failure, returns the last cached reading
    or a synthetic reading with value=16.0 (mid-normal range).
    """
    if _is_cache_valid():
        return _cache["reading"]  # type: ignore[return-value]

    try:
        reading = await fetch_india_vix(client)
        _store_in_cache(reading)
        return reading
    except Exception as exc:  # noqa: BLE001
        logger.warning("india_vix.fetch_failed", error=str(exc))

    # Return last known reading if available
    if "reading" in _cache:
        logger.info("india_vix.using_stale_cache")
        return _cache["reading"]  # type: ignore[return-value]

    # Absolute fallback: neutral VIX
    fallback = VixReading(
        value=_FALLBACK_VIX,
        change_pct=0.0,
        fetched_at=utcnow(),
    )
    logger.warning("india_vix.using_fallback", vix=_FALLBACK_VIX)
    return fallback
