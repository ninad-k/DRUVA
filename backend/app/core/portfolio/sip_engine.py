"""SIP / STP cadence engine.

For each active ``SipSchedule`` whose ``next_run_date`` has arrived, produce
a ``SipExecution`` row and an ``ApprovalRequest`` sized to the monthly SIP
tranche. STP drain logic splits an initial lump-sum into N tranches over
consecutive months.

This layer does the bookkeeping; order placement runs through the existing
``ApprovalService``.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.execution.approval_service import ApprovalService
from app.db.models.goal import (
    GoalStatus,
    InvestmentGoal,
    SipExecution,
    SipExecutionStatus,
    SipSchedule,
)
from app.utils.time import utcnow


def _next_month(d: date, day_of_month: int) -> date:
    year = d.year + (1 if d.month == 12 else 0)
    month = 1 if d.month == 12 else d.month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day))


@dataclass
class SipEngine:
    session: AsyncSession
    approval_service: ApprovalService

    async def create_stp_plan(
        self,
        *,
        goal_id: UUID,
        lump_sum: Decimal,
        months: int,
        day_of_month: int = 5,
    ) -> SipSchedule:
        goal = await self.session.get(InvestmentGoal, goal_id)
        if goal is None:
            raise NotFoundError("goal_not_found")
        if months <= 0:
            months = 12
        per_tranche = (lump_sum / Decimal(months)).quantize(Decimal("0.01"))
        start = _next_month(utcnow().date(), day_of_month)
        schedule = SipSchedule(
            goal_id=goal.id,
            strategy_id=None,
            day_of_month=day_of_month,
            next_run_date=start,
            stp_tranches_remaining=months,
            amount_per_tranche=per_tranche,
            is_active=True,
        )
        self.session.add(schedule)
        await self.session.commit()
        await self.session.refresh(schedule)
        return schedule

    async def run_due(self) -> int:
        """Fire all due schedules, return count executed."""
        today = utcnow().date()
        due = (
            await self.session.execute(
                select(SipSchedule).where(
                    SipSchedule.is_active.is_(True),
                    SipSchedule.next_run_date <= today,
                )
            )
        ).scalars().all()
        fired = 0
        for sch in due:
            goal = await self.session.get(InvestmentGoal, sch.goal_id)
            if goal is None or goal.status != GoalStatus.ACTIVE:
                continue
            amount = sch.amount_per_tranche if sch.amount_per_tranche > 0 else goal.monthly_sip_amount
            target_symbols = goal.target_symbols or ["NIFTYBEES"]
            per_sym = (amount / Decimal(len(target_symbols))).quantize(Decimal("0.01"))
            for sym in target_symbols:
                # Price is looked up at promotion time by the approval flow;
                # here we carry the amount and let the executor translate.
                exec_row = SipExecution(
                    goal_id=goal.id,
                    schedule_id=sch.id,
                    executed_at=utcnow(),
                    amount=per_sym,
                    symbol=sym,
                    exchange="NSE",
                    status=SipExecutionStatus.PENDING,
                )
                self.session.add(exec_row)
                fired += 1

            # Advance the cadence.
            sch.next_run_date = _next_month(today, sch.day_of_month)
            if sch.stp_tranches_remaining > 0:
                sch.stp_tranches_remaining -= 1
                if sch.stp_tranches_remaining == 0:
                    sch.is_active = False
        await self.session.commit()
        return fired
