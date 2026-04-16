"""Execution service — single entry-point for placing/cancelling/modifying orders.

Fixes versus the prior version:
- Real wall-clock latency recorded into ``order_place_duration_seconds``.
- Atomic basket: every leg shares one outer transaction; on any failure all
  prior legs roll back. The internal ``_place_one`` method does NOT commit; the
  outer ``place_order`` and ``basket_order`` decide when to commit.
- ApprovalRequest now links back to the Order it gates (``order_id``).
- ApprovalRequest expires after a configurable TTL (was previously ``utcnow()``,
  i.e. instantly expired).
- ``close_position`` reads the existing Position and reuses its real
  ``exchange``/``product`` (was hardcoded NSE/MIS).
- Strategy-driven orders use ``account.user_id`` as the actor, not a fake UUID.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAdapter, OrderRequest
from app.brokers.factory import BrokerFactory
from app.config import get_settings
from app.core.audit.event_store import AuditService
from app.core.errors import NotFoundError, RiskRejectedError, ValidationError
from app.core.execution.models import (
    BasketOrderRequest,
    ModifyOrderRequest,
    PlaceOrderRequest,
    SmartOrderRequest,
)
from app.core.execution.position_tracker import PositionTracker
from app.core.execution.risk_engine import RiskEngine
from app.db.models.account import Account
from app.db.models.approval import ApprovalRequest
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy
from app.infrastructure.logging import get_logger
from app.infrastructure.metrics import order_place_duration_seconds, orders_placed_total
from app.infrastructure.tracing import get_tracer
from app.strategies.base import Fill
from app.utils.time import utcnow

tracer = get_tracer(__name__)
logger = get_logger(__name__)


@dataclass
class ExecutionService:
    session: AsyncSession
    broker_factory: BrokerFactory
    audit_service: AuditService
    risk_engine: RiskEngine
    position_tracker: PositionTracker
    # Optional hook called after every successful fill — used to push Telegram
    # notifications without coupling the notifier into this module.
    on_fill: Callable[[Order], Awaitable[None]] | None = field(default=None)

    # ---------------------------------------------------------------- public

    async def place_order(self, user_id: str, req: PlaceOrderRequest) -> Order:
        """Place a single order with risk + audit; commits on success."""
        with tracer.start_as_current_span("execution.place_order"):
            order = await self._place_one(user_id, req)
            await self.session.commit()
            await self.session.refresh(order)
        if order.status == "filled" and self.on_fill is not None:
            try:
                await self.on_fill(order)
            except Exception as exc:  # noqa: BLE001
                logger.warning("execution.on_fill_failed", error=str(exc))
        return order

    async def smart_order(self, user_id: str, req: SmartOrderRequest) -> Order:
        """Place an order that brings the net position to ``target_quantity``.

        Computes ``delta = target - current``; emits a single MARKET/LIMIT order
        for ``abs(delta)`` on the appropriate side. Returns a synthetic zero-qty
        Order if no action is needed (no DB write).
        """
        current = await self.session.scalar(
            select(Position).where(
                Position.account_id == req.account_id,
                Position.symbol == req.symbol,
                Position.exchange == req.exchange,
            )
        )
        current_qty = current.quantity if current else Decimal("0")
        delta = req.target_quantity - current_qty
        if delta == 0:
            return Order(
                user_id=uuid.UUID(user_id),
                account_id=req.account_id,
                symbol=req.symbol,
                exchange=req.exchange,
                side="BUY",
                quantity=Decimal("0"),
                order_type=req.order_type,
                product=req.product,
                status="filled",
            )
        side = "BUY" if delta > 0 else "SELL"
        return await self.place_order(
            user_id,
            PlaceOrderRequest(
                account_id=req.account_id,
                symbol=req.symbol,
                exchange=req.exchange,
                side=side,
                quantity=abs(delta),
                order_type=req.order_type,
                product=req.product,
                price=req.price,
            ),
        )

    async def close_position(self, user_id: str, account_id: uuid.UUID, symbol: str) -> Order:
        """Flatten the open position for ``symbol`` using its real exchange/product."""
        position = await self.session.scalar(
            select(Position).where(
                Position.account_id == account_id,
                Position.symbol == symbol,
            )
        )
        if position is None or position.quantity == 0:
            raise NotFoundError("no_open_position")
        return await self.smart_order(
            user_id,
            SmartOrderRequest(
                account_id=account_id,
                symbol=symbol,
                exchange=position.exchange,
                target_quantity=Decimal("0"),
                product=position.product,
            ),
        )

    async def cancel_order(self, user_id: str, order_id: uuid.UUID) -> Order:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("order_not_found")
        if order.status in {"filled", "cancelled", "rejected"}:
            raise ValidationError("order_not_cancellable")
        # Best-effort broker-side cancel; ignore broker errors so DB stays consistent.
        if order.broker_order_id:
            account = await self.session.get(Account, order.account_id)
            if account is not None:
                broker = await self.broker_factory.create(account)
                try:
                    await broker.cancel_order(order.broker_order_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("execution.broker_cancel_failed", error=str(exc))
        order.status = "cancelled"
        await self.audit_service.record(
            action="order.cancelled",
            entity_type="Order",
            entity_id=str(order.id),
            old_value=None,
            new_value={"status": "cancelled"},
            user_id=user_id,
            ip=None,
            user_agent=None,
            session=self.session,
        )
        await self.session.commit()
        return order

    async def cancel_all(self, user_id: str, account_id: uuid.UUID) -> list[Order]:
        orders = (
            await self.session.execute(
                select(Order).where(
                    Order.account_id == account_id,
                    Order.status.in_(["pending", "accepted"]),
                )
            )
        ).scalars().all()
        results: list[Order] = []
        for order in orders:
            try:
                results.append(await self.cancel_order(user_id, order.id))
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "execution.cancel_all_partial",
                    order_id=str(order.id),
                    error=str(exc),
                )
        return results

    async def basket_order(self, user_id: str, req: BasketOrderRequest) -> list[Order]:
        """Place a basket. With ``atomic=True`` we own the transaction and roll
        back ALL legs on first failure. With ``atomic=False`` each leg commits
        independently and a partial result is returned.
        """
        if req.atomic:
            created: list[Order] = []
            try:
                for item in req.orders:
                    order = await self._place_one(user_id, PlaceOrderRequest(**item.model_dump()))
                    created.append(order)
                await self.session.commit()
                for order in created:
                    await self.session.refresh(order)
            except Exception:
                await self.session.rollback()
                raise
            return created
        # Non-atomic: each leg is its own transaction.
        out: list[Order] = []
        for item in req.orders:
            try:
                out.append(await self.place_order(user_id, PlaceOrderRequest(**item.model_dump())))
            except Exception as exc:  # noqa: BLE001
                logger.warning("execution.basket_leg_failed", error=str(exc))
        return out

    async def modify_order(
        self, user_id: str, order_id: uuid.UUID, req: ModifyOrderRequest
    ) -> Order:
        order = await self.session.get(Order, order_id)
        if order is None:
            raise NotFoundError("order_not_found")
        if req.quantity is not None:
            order.quantity = req.quantity
        if req.price is not None:
            order.price = req.price
        if req.trigger_price is not None:
            order.trigger_price = req.trigger_price
        if req.order_type is not None:
            order.order_type = req.order_type
        await self.audit_service.record(
            action="order.modified",
            entity_type="Order",
            entity_id=str(order.id),
            old_value=None,
            new_value=req.model_dump(mode="json", exclude_none=True),
            user_id=user_id,
            ip=None,
            user_agent=None,
            session=self.session,
        )
        await self.session.commit()
        return order

    async def list_orders(self, user_id: str, account_id: uuid.UUID) -> list[Order]:  # noqa: ARG002
        return (
            await self.session.execute(select(Order).where(Order.account_id == account_id))
        ).scalars().all()

    async def list_positions(self, account_id: uuid.UUID) -> list[Position]:
        return (
            await self.session.execute(select(Position).where(Position.account_id == account_id))
        ).scalars().all()

    # ---------------------------------------------------------------- internals

    async def _get_account(self, account_id: uuid.UUID, user_id: str) -> Account:
        account = await self.session.get(Account, account_id)
        if account is None or str(account.user_id) != user_id:
            raise NotFoundError("account_not_found")
        return account

    async def _place_one(self, user_id: str, req: PlaceOrderRequest) -> Order:
        """Inner placement that does NOT commit. Used by both ``place_order``
        (which commits on success) and the atomic-basket loop (which commits
        once at the end).
        """
        account = await self._get_account(req.account_id, user_id)

        # Build the broker (also used by the margin check) once.
        broker: BrokerAdapter = await self.broker_factory.create(account)

        risk = await self.risk_engine.validate(account, req, broker=broker)
        if not risk.passed:
            raise RiskRejectedError(risk.reason or "risk_failed")

        # Approval gate: when the originating strategy says so, persist a
        # ``pending_approval`` Order plus an ApprovalRequest linked to it.
        if req.strategy_id:
            strategy = await self.session.get(Strategy, req.strategy_id)
            if strategy and strategy.requires_approval:
                return await self._create_pending_approval(account, req, user_id)

        started = time.perf_counter()
        ack = await broker.place_order(
            OrderRequest(
                symbol=req.symbol,
                exchange=req.exchange,
                side=req.side,
                quantity=req.quantity,
                order_type=req.order_type,
                product=req.product,
                price=req.price,
                trigger_price=req.trigger_price,
                tag=req.tag,
            )
        )
        elapsed = time.perf_counter() - started
        order_place_duration_seconds.labels(broker=account.broker_id).observe(elapsed)

        is_filled = ack.status in {"filled", "accepted"}
        order = Order(
            user_id=uuid.UUID(user_id),
            account_id=req.account_id,
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            exchange=req.exchange,
            side=req.side,
            quantity=req.quantity,
            filled_quantity=req.quantity if is_filled else Decimal("0"),
            order_type=req.order_type,
            product=req.product,
            price=req.price,
            trigger_price=req.trigger_price,
            status="filled" if is_filled else "pending",
            broker_order_id=ack.broker_order_id,
            tag=req.tag,
        )
        self.session.add(order)
        await self.session.flush()

        if is_filled:
            fill = Fill(
                order_id=str(order.id),
                symbol=req.symbol,
                side=req.side,
                quantity=req.quantity,
                price=req.price or Decimal("0"),
                ts=utcnow(),
            )
            await self.position_tracker.apply_fill(fill, self.session)

        await self.audit_service.record(
            action="order.placed",
            entity_type="Order",
            entity_id=str(order.id),
            old_value=None,
            new_value={
                "status": order.status,
                "symbol": order.symbol,
                "side": order.side,
                "qty": str(order.quantity),
                "broker_order_id": order.broker_order_id,
                "latency_ms": round(elapsed * 1000, 3),
            },
            user_id=user_id,
            ip=None,
            user_agent=None,
            session=self.session,
        )
        orders_placed_total.labels(broker=account.broker_id, status=order.status).inc()
        return order

    async def _create_pending_approval(
        self, account: Account, req: PlaceOrderRequest, user_id: str
    ) -> Order:
        """Insert an Order in ``pending_approval`` status plus a linked ApprovalRequest."""
        settings = get_settings()
        order = Order(
            user_id=uuid.UUID(user_id),
            account_id=req.account_id,
            strategy_id=req.strategy_id,
            symbol=req.symbol,
            exchange=req.exchange,
            side=req.side,
            quantity=req.quantity,
            order_type=req.order_type,
            product=req.product,
            price=req.price,
            trigger_price=req.trigger_price,
            status="pending_approval",
            tag=req.tag,
        )
        self.session.add(order)
        await self.session.flush()

        approval = ApprovalRequest(
            account_id=req.account_id,
            strategy_id=req.strategy_id,
            order_id=order.id,
            signal_jsonb=req.model_dump(mode="json"),
            status="pending",
            requested_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=settings.approval_ttl_minutes),
        )
        self.session.add(approval)
        await self.audit_service.record(
            action="order.pending_approval",
            entity_type="Order",
            entity_id=str(order.id),
            old_value=None,
            new_value=req.model_dump(mode="json"),
            user_id=user_id,
            ip=None,
            user_agent=None,
            session=self.session,
        )
        return order
