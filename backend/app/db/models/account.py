from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import ProductType, TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    api_key_nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    api_secret_nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_product: Mapped[ProductType] = mapped_column(enum_col(ProductType, "product_type"), default=ProductType.MIS, nullable=False)
    paper_starting_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), default=Decimal("1000000"), nullable=False)
    # Health monitor enforces the "3 consecutive failures → disable" rule. The
    # counter has to persist across scheduler runs, so it lives on the row.
    consecutive_health_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When the monitor disables an account it stamps this; admins can ack/clear.
    health_disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
