from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import keys
from app.cache.client import CacheClient
from app.db.models.order import Order
from app.db.models.position import Position
from app.strategies.base import Fill


@dataclass
class PositionTracker:
    session: AsyncSession
    cache: CacheClient

    async def get(self, account_id: str, symbol: str) -> Position | None:
        return await self.session.scalar(
            select(Position).where(Position.account_id == account_id, Position.symbol == symbol)
        )

    async def get_all(self, account_id: str) -> list[Position]:
        return (
            await self.session.execute(select(Position).where(Position.account_id == account_id))
        ).scalars().all()

    async def apply_fill(self, fill: Fill, session: AsyncSession) -> Position:
        order = await session.scalar(select(Order).where(Order.id == fill.order_id))
        if order is None:
            raise ValueError("order_not_found")

        position = await session.scalar(
            select(Position).where(
                Position.account_id == order.account_id,
                Position.symbol == fill.symbol,
                Position.exchange == order.exchange,
            )
        )
        if position is None:
            position = Position(
                account_id=order.account_id,
                symbol=fill.symbol,
                exchange=order.exchange,
                product=order.product,
                quantity=0,
                avg_cost=0,
                realized_pnl=0,
            )
            session.add(position)
            await session.flush()

        signed_qty = fill.quantity if fill.side == "BUY" else -fill.quantity
        old_qty = position.quantity
        new_qty = old_qty + signed_qty
        if new_qty != 0:
            position.avg_cost = ((position.avg_cost * old_qty) + (fill.price * signed_qty)) / new_qty
        position.quantity = new_qty
        await self.cache.set_json(
            keys.position(str(position.account_id), position.symbol),
            {"id": str(position.id)},
            ttl=keys.TTL_POSITION,
        )
        return position
