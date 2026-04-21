"""Goal-based SIP/STP scanner (Strategy 2 — Shubham).

When today matches any active ``SipSchedule.next_run_date``, emit one
candidate per target symbol sized to the SIP tranche. STP tranches drain
the arbitrage buffer over N monthly transfers (default 12).

Promotion routes these through ``ApprovalService`` like any other signal.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scanner.base import ScanCandidate, ScanContext, Scanner
from app.core.scanner.registry import register_scanner
from app.db.models.goal import GoalStatus, InvestmentGoal, SipSchedule
from app.utils.time import utcnow


@register_scanner("scanner.goal_based_allocator.v1")
class GoalBasedAllocatorScanner(Scanner):

    async def scan(self, context: ScanContext) -> list[ScanCandidate]:
        session: AsyncSession = getattr(context, "session", None)  # type: ignore[assignment]
        if session is None:
            return []
        today = utcnow().date()

        schedules = (
            await session.execute(
                select(SipSchedule).where(
                    SipSchedule.is_active.is_(True),
                    SipSchedule.next_run_date <= today,
                )
            )
        ).scalars().all()
        if not schedules:
            return []

        out: list[ScanCandidate] = []
        for sch in schedules:
            goal = await session.get(InvestmentGoal, sch.goal_id)
            if goal is None or goal.status != GoalStatus.ACTIVE:
                continue
            if goal.account_id != context.account_id:
                # A single scanner run is scoped to one account at a time.
                continue

            amount = sch.amount_per_tranche or goal.monthly_sip_amount
            if amount <= 0:
                continue

            target_symbols = goal.target_symbols or ["NIFTYBEES"]
            per_symbol = amount / Decimal(len(target_symbols))
            for sym in target_symbols:
                candles = await context.get_candles(sym, "NSE", "1d", 5)
                price = Decimal(str(candles[-1].close)) if candles else Decimal("0")
                if price <= 0:
                    continue
                qty = (per_symbol / price).quantize(Decimal("1"))
                out.append(
                    ScanCandidate(
                        symbol=sym,
                        exchange="NSE",
                        score=0.9,
                        stage="sip_tranche",
                        reason=(
                            f"SIP goal={goal.name} amount={per_symbol} "
                            f"next_run={sch.next_run_date}"
                        ),
                        suggested_entry=price,
                        suggested_stop=None,
                        suggested_target=None,
                        metadata={
                            "goal_id": str(goal.id),
                            "schedule_id": str(sch.id),
                            "amount": str(per_symbol),
                            "qty": str(qty),
                        },
                    )
                )
        return out
