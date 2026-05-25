"""Calendar REST endpoints — Phase H.

GET  /api/v1/calendar/upcoming   → list upcoming events in a date range
GET  /api/v1/calendar/types      → list supported event types
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.auth.dependencies import get_current_user
from app.data.calendar.provider import CalendarEvent, build_calendar_provider

router = APIRouter()


class CalendarEventDTO(BaseModel):
    event_date: str
    event_type: str
    title: str
    symbol: str | None = None
    exchange: str | None = None
    description: str = ""
    time_utc: str | None = None
    impact: str | None = None
    metadata: dict[str, Any] = {}


def _to_dto(ev: CalendarEvent) -> CalendarEventDTO:
    return CalendarEventDTO(
        event_date=ev.event_date.isoformat(),
        event_type=ev.event_type,
        title=ev.title,
        symbol=ev.symbol,
        exchange=ev.exchange,
        description=ev.description,
        time_utc=ev.time_utc.isoformat() if ev.time_utc else None,
        impact=ev.impact,
        metadata=ev.metadata,
    )


@router.get("/upcoming", summary="List upcoming calendar events")
async def upcoming(
    from_date: date = Query(default_factory=date.today),
    to_date: date = Query(default_factory=date.today),
    event_types: str | None = Query(None, description="Comma-separated event types"),
    symbol: str | None = Query(None),
    _user=Depends(get_current_user),
) -> list[CalendarEventDTO]:
    provider = build_calendar_provider()
    types = [t.strip() for t in event_types.split(",")] if event_types else None
    events = await provider.upcoming(
        from_date=from_date,
        to_date=to_date,
        event_types=types,  # type: ignore[arg-type]
        symbol=symbol,
    )
    return [_to_dto(e) for e in events]


@router.get("/types", summary="List supported calendar event types")
async def event_types(_user=Depends(get_current_user)) -> list[str]:
    return ["dividend", "split", "bonus", "rights", "earnings", "rbi_mpc", "macro", "ipo", "other"]
