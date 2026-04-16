from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class PortfolioSnapshot(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "portfolio_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    margin_used: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class RebalancePlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "rebalance_plans"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
