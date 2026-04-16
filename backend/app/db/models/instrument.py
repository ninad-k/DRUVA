from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import (
    Exchange,
    InstrumentType,
    MasterContractSyncStatus,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    enum_col,
)


class Instrument(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("broker_id", "symbol", "exchange", name="uq_instrument_broker_symbol_exchange"),
        Index("ix_instruments_symbol", "symbol"),
    )

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_instrument"), nullable=False)
    broker_token: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_type: Mapped[InstrumentType] = mapped_column(enum_col(InstrumentType, "instrument_type"), nullable=False)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    lot_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tick_size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trading_symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class MasterContractStatus(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "master_contract_status"

    broker_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MasterContractSyncStatus] = mapped_column(
        enum_col(MasterContractSyncStatus, "master_contract_sync_status"),
        default=MasterContractSyncStatus.STALE,
        nullable=False,
    )
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class QtyFreezeLimit(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "qty_freeze_limits"
    __table_args__ = (Index("ix_qty_freeze_exchange_symbol", "exchange", "symbol"),)

    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_qty_freeze"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    qty_freeze: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
