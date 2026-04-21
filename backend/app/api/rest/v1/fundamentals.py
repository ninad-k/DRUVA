"""Fundamentals read + admin refresh endpoints."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.auth.dependencies import get_current_user
from app.data.fundamentals.refresh_job import FundamentalsRefreshJob
from app.data.fundamentals.repository import FundamentalRepository
from app.db.models.fundamentals import FundamentalSnapshot
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.http import get_http_client

router = APIRouter()


@router.get("/{symbol}")
async def get_fundamentals(
    symbol: str,
    exchange: str = Query("NSE"),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = FundamentalRepository(session=session)
    row = await repo.latest(symbol=symbol.upper(), exchange=exchange)
    if row is None:
        raise HTTPException(status_code=404, detail="fundamentals_not_found")
    return _to_dict(row)


@router.post("/refresh")
async def refresh(
    background: BackgroundTasks,
    limit: int = Query(50, ge=1, le=5000),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    http: httpx.AsyncClient | None = None
    async for client in get_http_client():
        http = client
        break
    if http is None:
        raise HTTPException(status_code=503, detail="http_client_unavailable")
    job = FundamentalsRefreshJob(session=session, http=http, settings=settings)

    async def _run() -> None:
        await job.run(limit=limit)

    background.add_task(_run)
    return {"status": "scheduled", "limit": limit}


def _to_dict(r: FundamentalSnapshot) -> dict[str, Any]:
    return {
        "symbol": r.symbol,
        "exchange": r.exchange,
        "as_of_date": r.as_of_date.isoformat(),
        "roe": float(r.roe) if r.roe is not None else None,
        "roce": float(r.roce) if r.roce is not None else None,
        "eps": float(r.eps) if r.eps is not None else None,
        "sales_growth_3y": float(r.sales_growth_3y) if r.sales_growth_3y is not None else None,
        "profit_growth_3y": float(r.profit_growth_3y) if r.profit_growth_3y is not None else None,
        "debt_to_equity": float(r.debt_to_equity) if r.debt_to_equity is not None else None,
        "promoter_holding": float(r.promoter_holding) if r.promoter_holding is not None else None,
        "market_cap": float(r.market_cap) if r.market_cap is not None else None,
        "current_price": float(r.current_price) if r.current_price is not None else None,
        "pe_ratio": float(r.pe_ratio) if r.pe_ratio is not None else None,
        "sector": r.sector,
        "industry": r.industry,
        "source": r.source,
    }
