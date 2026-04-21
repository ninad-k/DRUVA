"""Watchlist CRUD endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.db.models.user import User
from app.db.models.watchlist import Watchlist, WatchlistItem
from app.db.session import get_session

router = APIRouter()


class WatchlistCreate(BaseModel):
    account_id: UUID
    name: str
    description: str | None = None
    is_default: bool = False


class WatchlistItemCreate(BaseModel):
    symbol: str
    exchange: str = "NSE"
    source_scanner_id: UUID | None = None
    notes: str | None = None


@router.post("", status_code=201)
async def create_watchlist(
    payload: WatchlistCreate,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = Watchlist(**payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _to_dict(row)


@router.get("")
async def list_watchlists(
    account_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Watchlist).where(Watchlist.account_id == account_id)
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


@router.get("/{watchlist_id}/items")
async def list_items(
    watchlist_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == watchlist_id)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "watchlist_id": str(r.watchlist_id),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "source_scanner_id": str(r.source_scanner_id) if r.source_scanner_id else None,
            "notes": r.notes,
        }
        for r in rows
    ]


@router.post("/{watchlist_id}/items")
async def add_item(
    watchlist_id: UUID,
    payload: WatchlistItemCreate,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    wl = await session.get(Watchlist, watchlist_id)
    if wl is None:
        raise HTTPException(status_code=404, detail="watchlist_not_found")
    row = WatchlistItem(watchlist_id=wl.id, **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": str(row.id),
        "symbol": row.symbol,
        "exchange": row.exchange,
        "notes": row.notes,
    }


@router.delete("/{watchlist_id}/items/{item_id}")
async def remove_item(
    watchlist_id: UUID,
    item_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await session.get(WatchlistItem, item_id)
    if row is None or row.watchlist_id != watchlist_id:
        raise HTTPException(status_code=404, detail="item_not_found")
    await session.delete(row)
    await session.commit()
    return {"status": "deleted"}


def _to_dict(w: Watchlist) -> dict[str, Any]:
    return {
        "id": str(w.id),
        "account_id": str(w.account_id),
        "name": w.name,
        "description": w.description,
        "is_default": w.is_default,
    }
