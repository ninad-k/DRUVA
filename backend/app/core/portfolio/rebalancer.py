"""Target-allocation rebalancer.

Given a desired allocation (``{symbol: pct}``) and the account's current
positions, produce a list of BUY/SELL deltas to reach the target. Users
preview the plan in the UI and execute through ApprovalService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from math import floor
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.instrument import Instrument
from app.db.models.position import Position


@dataclass
class RebalanceLeg:
    symbol: str
    exchange: str
    side: str  # BUY | SELL
    quantity: Decimal
    current_qty: Decimal
    target_qty: Decimal
    reason: str = ""


@dataclass
class RebalancePlan:
    account_id: UUID
    legs: list[RebalanceLeg] = field(default_factory=list)
    estimated_turnover: Decimal = Decimal("0")


@dataclass
class Rebalancer:
    session: AsyncSession

    async def plan(
        self,
        *,
        account_id: UUID,
        broker_id: str,
        total_equity_inr: Decimal,
        target_allocation_pct: dict[str, Decimal],
        prices: dict[str, Decimal],
        exchange: str = "NSE",
    ) -> RebalancePlan:
        positions = (
            await self.session.execute(
                select(Position).where(Position.account_id == account_id)
            )
        ).scalars().all()
        current: dict[str, Decimal] = {p.symbol: p.quantity for p in positions}
        lots: dict[str, int] = {}
        for sym in target_allocation_pct.keys() | current.keys():
            inst = (
                await self.session.execute(
                    select(Instrument).where(
                        Instrument.symbol == sym,
                        Instrument.broker_id == broker_id,
                        Instrument.exchange == exchange,
                    )
                )
            ).scalar_one_or_none()
            lots[sym] = inst.lot_size if inst else 1

        plan = RebalancePlan(account_id=account_id)
        turnover = Decimal("0")
        # First pass: handle explicitly-targeted symbols.
        for sym, pct in target_allocation_pct.items():
            price = prices.get(sym, Decimal("0"))
            if price <= 0:
                continue
            target_notional = total_equity_inr * (pct / Decimal("100"))
            lot = lots.get(sym, 1)
            raw_qty = target_notional / price
            target_qty = Decimal(floor(raw_qty / max(lot, 1))) * Decimal(max(lot, 1))
            cur = current.get(sym, Decimal("0"))
            delta = target_qty - cur
            if delta == 0:
                continue
            plan.legs.append(
                RebalanceLeg(
                    symbol=sym,
                    exchange=exchange,
                    side="BUY" if delta > 0 else "SELL",
                    quantity=abs(delta),
                    current_qty=cur,
                    target_qty=target_qty,
                    reason="target_allocation",
                )
            )
            turnover += abs(delta) * price

        # Second pass: liquidate positions not in the target.
        for sym, cur in current.items():
            if sym in target_allocation_pct or cur == 0:
                continue
            price = prices.get(sym, Decimal("0"))
            plan.legs.append(
                RebalanceLeg(
                    symbol=sym,
                    exchange=exchange,
                    side="SELL",
                    quantity=abs(cur),
                    current_qty=cur,
                    target_qty=Decimal("0"),
                    reason="drop_from_target",
                )
            )
            if price > 0:
                turnover += abs(cur) * price

        plan.estimated_turnover = turnover
        return plan
