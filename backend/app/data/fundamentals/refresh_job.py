"""Weekly fundamentals refresh job.

Iterates the NSE+BSE equity universe, fetches Screener ratios, and upserts
``FundamentalSnapshot`` rows. Skips symbols whose latest snapshot is fresher
than ``settings.fundamentals_stale_days``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.scanner.universe import UniverseProvider
from app.data.fundamentals.repository import FundamentalRepository
from app.data.fundamentals.screener_client import ScreenerClient
from app.db.models.fundamentals import FundamentalSnapshot
from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass
class FundamentalsRefreshJob:
    session: AsyncSession
    http: httpx.AsyncClient
    settings: Settings

    async def run(self, *, limit: int | None = None) -> dict[str, Any]:
        today = utcnow().date()
        cutoff: date = today - timedelta(days=self.settings.fundamentals_stale_days)

        # Build the set of (symbol, exchange) already fresh.
        rows = (
            await self.session.execute(
                select(
                    FundamentalSnapshot.symbol, FundamentalSnapshot.exchange,
                ).where(FundamentalSnapshot.as_of_date >= cutoff)
            )
        ).all()
        fresh = {(r.symbol, r.exchange) for r in rows}

        universe = await UniverseProvider(session=self.session).list()
        to_refresh = [u for u in universe if (u.symbol, u.exchange) not in fresh]
        if limit is not None:
            to_refresh = to_refresh[:limit]

        client = ScreenerClient(
            http=self.http,
            base_url=self.settings.screener_base_url,
            max_concurrency=self.settings.fundamentals_max_concurrency,
        )
        repo = FundamentalRepository(session=self.session)

        async def _refresh_one(sym: str, exch: str) -> bool:
            data = await client.fetch(sym)
            if not data:
                return False
            await repo.upsert(
                symbol=sym, exchange=exch, as_of_date=today, data=data,
            )
            return True

        ok = 0
        errors = 0
        # Stream concurrency through asyncio.gather batches to honor the semaphore.
        batch_size = max(self.settings.fundamentals_max_concurrency * 4, 8)
        for i in range(0, len(to_refresh), batch_size):
            batch = to_refresh[i : i + batch_size]
            results = await asyncio.gather(
                *[_refresh_one(u.symbol, u.exchange) for u in batch],
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    errors += 1
                    logger.warning("fundamentals.refresh_error", error=str(r))
                elif r:
                    ok += 1

        logger.info(
            "fundamentals.refresh_complete",
            ok=ok,
            errors=errors,
            skipped=len(universe) - len(to_refresh),
        )
        return {
            "ok": ok,
            "errors": errors,
            "skipped": len(universe) - len(to_refresh),
            "attempted": len(to_refresh),
        }
