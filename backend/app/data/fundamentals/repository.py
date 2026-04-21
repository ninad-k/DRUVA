"""Async repo for ``FundamentalSnapshot``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.fundamentals import FundamentalSnapshot
from app.utils.time import utcnow


@dataclass
class FundamentalRepository:
    session: AsyncSession

    async def latest(
        self, *, symbol: str, exchange: str = "NSE",
    ) -> FundamentalSnapshot | None:
        return (
            await self.session.execute(
                select(FundamentalSnapshot)
                .where(
                    FundamentalSnapshot.symbol == symbol,
                    FundamentalSnapshot.exchange == exchange,
                )
                .order_by(FundamentalSnapshot.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def as_of(
        self, *, symbol: str, exchange: str, as_of: date,
    ) -> FundamentalSnapshot | None:
        return (
            await self.session.execute(
                select(FundamentalSnapshot)
                .where(
                    FundamentalSnapshot.symbol == symbol,
                    FundamentalSnapshot.exchange == exchange,
                    FundamentalSnapshot.as_of_date <= as_of,
                )
                .order_by(FundamentalSnapshot.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def upsert(
        self,
        *,
        symbol: str,
        exchange: str,
        as_of_date: date,
        data: dict[str, Any],
        source: str = "screener",
    ) -> FundamentalSnapshot:
        existing = (
            await self.session.execute(
                select(FundamentalSnapshot).where(
                    FundamentalSnapshot.symbol == symbol,
                    FundamentalSnapshot.exchange == exchange,
                    FundamentalSnapshot.as_of_date == as_of_date,
                )
            )
        ).scalar_one_or_none()

        def _dec(v: Any) -> Decimal | None:
            if v is None:
                return None
            if isinstance(v, Decimal):
                return v
            try:
                return Decimal(str(v))
            except Exception:  # noqa: BLE001
                return None

        if existing is None:
            row = FundamentalSnapshot(
                symbol=symbol,
                exchange=exchange,
                as_of_date=as_of_date,
                source=source,
                raw_jsonb={
                    k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()
                },
            )
            self.session.add(row)
            existing = row

        existing.roe = _dec(data.get("roe"))
        existing.roce = _dec(data.get("roce"))
        existing.eps = _dec(data.get("eps"))
        existing.sales_growth_3y = _dec(data.get("sales_growth_3y"))
        existing.profit_growth_3y = _dec(data.get("profit_growth_3y"))
        existing.debt_to_equity = _dec(data.get("debt_to_equity"))
        existing.promoter_holding = _dec(data.get("promoter_holding"))
        existing.market_cap = _dec(data.get("market_cap"))
        existing.current_price = _dec(data.get("current_price"))
        existing.pe_ratio = _dec(data.get("pe_ratio"))
        existing.sector = data.get("sector")
        existing.industry = data.get("industry")
        existing.raw_jsonb = {
            k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()
        }
        await self.session.commit()
        return existing

    async def stale(self, *, days: int = 7) -> list[tuple[str, str]]:
        """Return (symbol, exchange) pairs missing or older than ``days``."""
        cutoff: date = (utcnow() - timedelta(days=days)).date()
        rows = (
            await self.session.execute(
                select(
                    FundamentalSnapshot.symbol,
                    FundamentalSnapshot.exchange,
                    FundamentalSnapshot.as_of_date,
                ).where(FundamentalSnapshot.as_of_date >= cutoff)
            )
        ).all()
        fresh = {(r.symbol, r.exchange) for r in rows}
        # Caller intersects with the universe to decide which to refresh.
        return sorted(fresh)
