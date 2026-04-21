"""Market-cycle regime endpoints."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.scanner.market_cycle import MarketCycleRegimeDetector
from app.db.models.market_cycle import MarketCycleState
from app.db.models.user import User
from app.db.session import get_session
from app.utils.time import utcnow

router = APIRouter()


@router.get("/current")
async def current(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(MarketCycleState)
            .order_by(MarketCycleState.as_of_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="no_market_cycle")
    return _to_dict(row)


@router.get("/history")
async def history(
    days: int = Query(90, ge=1, le=730),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    cutoff = (utcnow() - timedelta(days=days)).date()
    rows = (
        await session.execute(
            select(MarketCycleState)
            .where(MarketCycleState.as_of_date >= cutoff)
            .order_by(MarketCycleState.as_of_date.asc())
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


@router.post("/recompute")
async def recompute(
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    detector = MarketCycleRegimeDetector(session=session)
    result = await detector.compute()
    row = await detector.upsert_today(result)
    return _to_dict(row)


def _to_dict(r: MarketCycleState) -> dict[str, Any]:
    return {
        "as_of_date": r.as_of_date.isoformat(),
        "regime": str(r.regime),
        "nifty_roc_18m": float(r.nifty_roc_18m) if r.nifty_roc_18m is not None else None,
        "smallcap_roc_20m": float(r.smallcap_roc_20m) if r.smallcap_roc_20m is not None else None,
        "suggested_allocation_pct": float(r.suggested_allocation_pct),
        "breadth_score": float(r.breadth_score) if r.breadth_score is not None else None,
        "note": r.note,
    }
