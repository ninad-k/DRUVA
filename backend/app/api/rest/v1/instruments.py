from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_broker_factory
from app.core.audit.event_store import AuditService
from app.data.instruments.sync_service import InstrumentSyncService
from app.db.models.calendar import MarketHoliday, MarketSession
from app.db.models.instrument import Instrument, MasterContractStatus
from app.db.session import get_session

router = APIRouter()


@router.get("/instruments/search")
async def search_instruments(
    q: str,
    exchange: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    query = select(Instrument).where(Instrument.symbol.ilike(f"%{q}%"))
    if exchange:
        query = query.where(Instrument.exchange == exchange)
    rows = (await session.execute(query.limit(limit))).scalars().all()
    return [
        {
            "id": str(row.id),
            "symbol": row.symbol,
            "exchange": str(row.exchange),
            "broker_id": row.broker_id,
            "trading_symbol": row.trading_symbol,
        }
        for row in rows
    ]


@router.get("/instruments/master-status")
async def master_status(session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    rows = (await session.execute(select(MasterContractStatus))).scalars().all()
    return [
        {
            "broker_id": row.broker_id,
            "status": str(row.status),
            "last_synced_at": row.last_synced_at.isoformat() if row.last_synced_at else None,
            "record_count": row.record_count,
        }
        for row in rows
    ]


@router.get("/instruments/{symbol}")
async def instrument_details(symbol: str, exchange: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    row = await session.scalar(select(Instrument).where(Instrument.symbol == symbol, Instrument.exchange == exchange))
    if row is None:
        return {}
    return {
        "id": str(row.id),
        "symbol": row.symbol,
        "exchange": str(row.exchange),
        "instrument_type": str(row.instrument_type),
        "lot_size": row.lot_size,
        "tick_size": str(row.tick_size),
    }


@router.post("/admin/instruments/sync")
async def sync_instruments(
    broker_id: str,
    session: AsyncSession = Depends(get_session),
    factory=Depends(get_broker_factory),
) -> dict[str, object]:
    service = InstrumentSyncService(session=session, factory=factory, audit_service=AuditService())
    result = await service.sync_broker(broker_id)
    return {"broker_id": result.broker_id, "records": result.records, "status": result.status}


@router.get("/calendar/holidays")
async def holidays(exchange: str, year: int, session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(MarketHoliday).where(
                MarketHoliday.exchange == exchange,
                MarketHoliday.holiday_date >= datetime(year, 1, 1, tzinfo=UTC).date(),
                MarketHoliday.holiday_date <= datetime(year, 12, 31, tzinfo=UTC).date(),
            )
        )
    ).scalars().all()
    return [{"date": row.holiday_date.isoformat(), "description": row.description} for row in rows]


@router.get("/calendar/sessions")
async def sessions(exchange: str, session: AsyncSession = Depends(get_session)) -> list[dict[str, object]]:
    rows = (await session.execute(select(MarketSession).where(MarketSession.exchange == exchange))).scalars().all()
    return [
        {
            "weekday": row.weekday,
            "open_time": row.open_time.isoformat(),
            "close_time": row.close_time.isoformat(),
            "session_type": str(row.session_type),
        }
        for row in rows
    ]


@router.get("/calendar/is-open")
async def is_open(exchange: str, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    now = datetime.now(UTC)
    holiday = await session.scalar(
        select(MarketHoliday).where(MarketHoliday.exchange == exchange, MarketHoliday.holiday_date == now.date())
    )
    if holiday is not None:
        return {"open": False, "opens_at": None, "closes_at": None}
    rows = (
        await session.execute(
            select(MarketSession).where(MarketSession.exchange == exchange, MarketSession.weekday == now.weekday())
        )
    ).scalars().all()
    for row in rows:
        if row.open_time <= now.time().replace(tzinfo=None) <= row.close_time:
            opens_at = datetime.combine(now.date(), row.open_time, tzinfo=UTC)
            closes_at = datetime.combine(now.date(), row.close_time, tzinfo=UTC)
            return {"open": True, "opens_at": opens_at.isoformat(), "closes_at": closes_at.isoformat()}
    return {"open": False, "opens_at": None, "closes_at": None}
