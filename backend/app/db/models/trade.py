from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import Exchange, OrderSide, ProductType, TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "trades"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_trade"), nullable=False)
    side: Mapped[OrderSide] = mapped_column(enum_col(OrderSide, "order_side_trade"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    product: Mapped[ProductType] = mapped_column(enum_col(ProductType, "product_type_trade"), nullable=False)
    broker_trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
