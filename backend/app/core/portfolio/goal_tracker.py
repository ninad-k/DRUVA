"""Progress + projection for investment goals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.goal import InvestmentGoal, SipExecution


@dataclass
class GoalProgress:
    goal_id: UUID
    name: str
    target_amount: Decimal
    target_date: date
    current_value: Decimal
    progress_pct: Decimal
    months_remaining: int
    projected_value: Decimal
    required_monthly: Decimal


@dataclass
class GoalTracker:
    session: AsyncSession

    async def progress(self, *, goal_id: UUID, as_of: date) -> GoalProgress:
        goal = await self.session.get(InvestmentGoal, goal_id)
        if goal is None:
            raise ValueError("goal_not_found")

        # Executed SIPs add to the current value (paper projection).
        execs = (
            await self.session.execute(
                select(SipExecution).where(SipExecution.goal_id == goal.id)
            )
        ).scalars().all()
        invested = sum((e.amount for e in execs), Decimal("0"))
        current = goal.current_value or Decimal("0")
        if current == 0:
            current = invested

        target = goal.target_amount
        pct = (current / target * Decimal("100")).quantize(Decimal("0.01")) if target > 0 else Decimal("0")

        months_remaining = max(
            0,
            (goal.target_date.year - as_of.year) * 12 + (goal.target_date.month - as_of.month),
        )
        projected = current + (goal.monthly_sip_amount * Decimal(months_remaining))
        shortfall = max(Decimal("0"), target - current)
        required_monthly = (
            (shortfall / Decimal(months_remaining)).quantize(Decimal("0.01"))
            if months_remaining > 0
            else shortfall
        )
        return GoalProgress(
            goal_id=goal.id,
            name=goal.name,
            target_amount=target,
            target_date=goal.target_date,
            current_value=current,
            progress_pct=pct,
            months_remaining=months_remaining,
            projected_value=projected,
            required_monthly=required_monthly,
        )
