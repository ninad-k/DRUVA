"""Dashboard analytics endpoints.

Computed from local DB state — no broker round-trips. For paper accounts the
equity curve is derived from ``Account.paper_starting_capital`` plus realized
P&L from positions; for live accounts the same shape is used until a broker
sync populates positions. This is honest data: zero P&L if no orders have been
filled, not a random-walk mock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.db.models.account import Account
from app.db.models.common import OrderStatus
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter()


async def _load_account(
    account_id: UUID, user: User, session: AsyncSession
) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="account_not_found")
    return account


def _starting_capital(account: Account) -> Decimal:
    # Cash balance is now persisted on the account and refreshed on each
    # broker sync (paper: seeded from paper_starting_capital at create-time,
    # live: read from adapter.get_margin().available_cash). The
    # paper_starting_capital fallback is kept for accounts that pre-date the
    # cash_balance column.
    if account.cash_balance and account.cash_balance > 0:
        return account.cash_balance
    if account.is_paper:
        return account.paper_starting_capital
    return Decimal("0")


def _decimal_to_float(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


@router.get("/summary")
async def summary(
    account_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    account = await _load_account(account_id, user, session)

    positions = (
        await session.execute(select(Position).where(Position.account_id == account.id))
    ).scalars().all()
    strategies = (
        await session.execute(select(Strategy).where(Strategy.account_id == account.id))
    ).scalars().all()

    realized_pnl = sum((p.realized_pnl for p in positions), Decimal("0"))
    # Equity = cash + cost-basis of open positions + realized P&L. Cost basis
    # stands in for market value until a quote service is wired into analytics;
    # for closed-out books cash already reflects exits, so this matches.
    holdings_book_value = sum(
        (p.quantity * p.avg_cost for p in positions if p.quantity != 0),
        Decimal("0"),
    )
    total_equity = _starting_capital(account) + holdings_book_value + realized_pnl

    open_positions = sum(1 for p in positions if p.quantity != 0)
    active_strategies = sum(1 for s in strategies if s.is_enabled)

    # Day P&L: orders filled today (UTC) — sum of (filled_qty * price) signed.
    # Approximation until we wire a true mark-to-market.
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders = (
        await session.execute(
            select(Order).where(
                Order.account_id == account.id,
                Order.status == OrderStatus.FILLED,
                Order.created_at >= today_start,
            )
        )
    ).scalars().all()
    day_pnl = Decimal("0")
    for o in today_orders:
        if o.price is None:
            continue
        signed_qty = o.filled_quantity if o.side.value == "SELL" else -o.filled_quantity
        day_pnl += signed_qty * o.price

    denominator = total_equity if total_equity > 0 else Decimal("1")
    day_pnl_pct = float(day_pnl / denominator * Decimal("100"))

    return {
        "total_equity": _decimal_to_float(total_equity),
        "cash_balance": _decimal_to_float(account.cash_balance),
        "holdings_value": _decimal_to_float(holdings_book_value),
        "day_pnl": _decimal_to_float(day_pnl),
        "day_pnl_pct": day_pnl_pct,
        "open_positions": open_positions,
        "total_positions": len(positions),
        "active_strategies": active_strategies,
        "total_strategies": len(strategies),
        "last_synced_at": account.last_synced_at.isoformat() if account.last_synced_at else None,
    }


@router.get("/equity-curve")
async def equity_curve(
    account_id: UUID = Query(...),
    days: int = Query(60, ge=1, le=365),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    account = await _load_account(account_id, user, session)
    start = (datetime.now(UTC) - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    orders = (
        await session.execute(
            select(Order)
            .where(
                Order.account_id == account.id,
                Order.status == OrderStatus.FILLED,
                Order.created_at >= start,
            )
            .order_by(Order.created_at.asc())
        )
    ).scalars().all()

    starting = _starting_capital(account)
    # Walk forward day-by-day. On a fresh account this stays flat at `starting`.
    points: list[dict[str, Any]] = []
    running = starting
    order_idx = 0
    for offset in range(days):
        day = (start + timedelta(days=offset)).date()
        day_end = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
        while order_idx < len(orders) and orders[order_idx].created_at <= day_end:
            o = orders[order_idx]
            if o.price is not None:
                signed = o.filled_quantity if o.side.value == "SELL" else -o.filled_quantity
                running += signed * o.price
            order_idx += 1
        points.append({"ts": day.isoformat(), "equity": _decimal_to_float(running)})

    return points
