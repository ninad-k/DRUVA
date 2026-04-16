from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LatencySample(Base):
    __tablename__ = "latency_samples"
    __table_args__ = (Index("ix_latency_broker_ts", "broker_id", "ts"),)

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    latency_ms: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
