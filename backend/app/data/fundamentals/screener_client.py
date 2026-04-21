"""httpx-based Screener.in client with concurrency cap + jittered backoff.

Respects Screener's implicit rate limit: at most 4 concurrent connections,
~1s jitter between hits per-host. On 403/429 we back off exponentially.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


USER_AGENT = (
    "Mozilla/5.0 (DHRUVA fundamentals fetcher; https://github.com/dhruva-platform)"
)


@dataclass
class ScreenerClient:
    http: httpx.AsyncClient
    base_url: str = "https://www.screener.in"
    max_concurrency: int = 4
    min_delay_s: float = 0.5
    max_delay_s: float = 1.5
    _sem: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self._sem = asyncio.Semaphore(self.max_concurrency)

    async def fetch(self, symbol: str) -> dict[str, Any] | None:
        """Return parsed ratios dict or None on hard failure."""
        from app.data.fundamentals.parser import parse_ratios

        url = f"{self.base_url}/company/{symbol.upper()}/consolidated/"
        async with self._sem:
            # Jitter to smooth bursts.
            await asyncio.sleep(random.uniform(self.min_delay_s, self.max_delay_s))
            for attempt in range(3):
                try:
                    resp = await self.http.get(
                        url, headers={"User-Agent": USER_AGENT}, timeout=15.0,
                    )
                except httpx.HTTPError as exc:
                    logger.info(
                        "screener.fetch_error", symbol=symbol, attempt=attempt, error=str(exc),
                    )
                    await asyncio.sleep(2 ** attempt)
                    continue
                if resp.status_code == 200:
                    break
                if resp.status_code in (403, 429):
                    logger.info(
                        "screener.backoff", symbol=symbol, status=resp.status_code,
                    )
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                if resp.status_code == 404:
                    # Try the non-consolidated URL as a fallback.
                    url = f"{self.base_url}/company/{symbol.upper()}/"
                    continue
                logger.info(
                    "screener.unexpected_status", symbol=symbol, status=resp.status_code,
                )
                return None
            else:
                return None

            try:
                data = parse_ratios(resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.warning("screener.parse_failed", symbol=symbol, error=str(exc))
                return None
            if not data:
                return None
            # Normalise some numeric shapes.
            for key in ("roe", "roce", "debt_to_equity", "promoter_holding"):
                if key in data and not isinstance(data[key], Decimal):
                    try:
                        data[key] = Decimal(str(data[key]))
                    except Exception:  # noqa: BLE001
                        data.pop(key)
            return data
