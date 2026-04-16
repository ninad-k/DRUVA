from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import (
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_col,
)


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange"), nullable=False)
    side: Mapped[OrderSide] = mapped_column(enum_col(OrderSide, "order_side"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(enum_col(OrderType, "order_type"), nullable=False)
    product: Mapped[ProductType] = mapped_column(enum_col(ProductType, "product_type_orders"), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(enum_col(OrderStatus, "order_status"), default=OrderStatus.PENDING, nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
