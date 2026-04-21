"""Investment goals + SIP/STP endpoints."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_approval_service
from app.core.auth.dependencies import get_current_user
from app.core.execution.approval_service import ApprovalService
from app.core.portfolio.goal_tracker import GoalTracker
from app.core.portfolio.sip_engine import SipEngine
from app.db.models.goal import (
    GoalStatus,
    InvestmentGoal,
    SipExecution,
    SipSchedule,
)
from app.db.models.user import User
from app.db.session import get_session
from app.utils.time import utcnow

router = APIRouter()


class GoalCreate(BaseModel):
    account_id: UUID
    name: str
    target_amount: float
    target_date: date
    monthly_sip_amount: float = 0.0
    arbitrage_buffer_pct: float = 0.0
    equity_allocation_pct: float = 80.0
    target_symbols: list[str] = []


class StpPlan(BaseModel):
    lump_sum: float
    months: int = 12
    day_of_month: int = 5


@router.post("", status_code=201)
async def create_goal(
    payload: GoalCreate,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    goal = InvestmentGoal(
        account_id=payload.account_id,
        name=payload.name,
        target_amount=Decimal(str(payload.target_amount)),
        target_date=payload.target_date,
        monthly_sip_amount=Decimal(str(payload.monthly_sip_amount)),
        arbitrage_buffer_pct=Decimal(str(payload.arbitrage_buffer_pct)),
        equity_allocation_pct=Decimal(str(payload.equity_allocation_pct)),
        target_symbols=payload.target_symbols,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return _to_dict(goal)


@router.get("")
async def list_goals(
    account_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(InvestmentGoal).where(InvestmentGoal.account_id == account_id)
        )
    ).scalars().all()
    return [_to_dict(r) for r in rows]


@router.get("/{goal_id}")
async def get_goal(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    goal = await session.get(InvestmentGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal_not_found")
    return _to_dict(goal)


@router.get("/{goal_id}/progress")
async def progress(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    tracker = GoalTracker(session=session)
    p = await tracker.progress(goal_id=goal_id, as_of=utcnow().date())
    return {
        "goal_id": str(p.goal_id),
        "name": p.name,
        "target_amount": str(p.target_amount),
        "target_date": p.target_date.isoformat(),
        "current_value": str(p.current_value),
        "progress_pct": str(p.progress_pct),
        "months_remaining": p.months_remaining,
        "projected_value": str(p.projected_value),
        "required_monthly": str(p.required_monthly),
    }


@router.post("/{goal_id}/stp-plan")
async def create_stp(
    goal_id: UUID,
    payload: StpPlan,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> dict[str, Any]:
    engine = SipEngine(session=session, approval_service=approval_service)
    sch = await engine.create_stp_plan(
        goal_id=goal_id,
        lump_sum=Decimal(str(payload.lump_sum)),
        months=payload.months,
        day_of_month=payload.day_of_month,
    )
    return {
        "schedule_id": str(sch.id),
        "next_run_date": sch.next_run_date.isoformat(),
        "amount_per_tranche": str(sch.amount_per_tranche),
        "tranches_remaining": sch.stp_tranches_remaining,
    }


@router.get("/{goal_id}/schedules")
async def list_schedules(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SipSchedule).where(SipSchedule.goal_id == goal_id)
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "goal_id": str(r.goal_id),
            "day_of_month": r.day_of_month,
            "next_run_date": r.next_run_date.isoformat(),
            "is_active": r.is_active,
            "tranches_remaining": r.stp_tranches_remaining,
            "amount_per_tranche": str(r.amount_per_tranche),
        }
        for r in rows
    ]


@router.get("/{goal_id}/executions")
async def list_executions(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(SipExecution)
            .where(SipExecution.goal_id == goal_id)
            .order_by(SipExecution.executed_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "executed_at": r.executed_at.isoformat(),
            "amount": str(r.amount),
            "symbol": r.symbol,
            "exchange": r.exchange,
            "status": str(r.status),
        }
        for r in rows
    ]


@router.post("/{goal_id}/pause")
async def pause(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    goal = await session.get(InvestmentGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal_not_found")
    goal.status = GoalStatus.PAUSED
    await session.commit()
    return _to_dict(goal)


@router.post("/{goal_id}/resume")
async def resume(
    goal_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    goal = await session.get(InvestmentGoal, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="goal_not_found")
    goal.status = GoalStatus.ACTIVE
    await session.commit()
    return _to_dict(goal)


def _to_dict(g: InvestmentGoal) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "account_id": str(g.account_id),
        "name": g.name,
        "target_amount": str(g.target_amount),
        "target_date": g.target_date.isoformat(),
        "current_value": str(g.current_value),
        "monthly_sip_amount": str(g.monthly_sip_amount),
        "arbitrage_buffer_pct": str(g.arbitrage_buffer_pct),
        "equity_allocation_pct": str(g.equity_allocation_pct),
        "status": str(g.status),
        "target_symbols": g.target_symbols or [],
    }
