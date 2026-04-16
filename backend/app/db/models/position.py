from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import Exchange, ProductType, TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class Position(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("account_id", "symbol", "exchange", name="uq_position_symbol"),)

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_position"), nullable=False)
    product: Mapped[ProductType] = mapped_column(enum_col(ProductType, "product_type_position"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"), nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("0"), nullable=False)
