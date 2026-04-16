from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OhlcvCandle(Base):
    __tablename__ = "ohlcv_candles"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(16), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(8), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class OrderEvent(Base):
    __tablename__ = "order_events"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class PnlSnapshot(Base):
    __tablename__ = "pnl_snapshots"

    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), primary_key=True)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
