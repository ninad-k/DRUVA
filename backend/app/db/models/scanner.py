"""Scanner framework persistence models.

- ``scanner_configs`` — per-account scanner registration (class, parameters, cadence).
- ``scan_results``    — candidates emitted by each scanner run.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class ScanResultStatus(str, enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    PROMOTED = "promoted"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class ScannerCadence(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"


class ScannerConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scanner_configs"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scanner_class: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    cadence: Mapped[ScannerCadence] = mapped_column(
        enum_col(ScannerCadence, "scanner_cadence"),
        default=ScannerCadence.DAILY,
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ScanResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "scan_results"
    __table_args__ = (
        Index("ix_scan_results_scanner_status", "scanner_id", "status"),
        Index("ix_scan_results_symbol_run", "symbol", "run_ts"),
    )

    scanner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scanner_configs.id", ondelete="CASCADE"), nullable=False,
    )
    run_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("0"))
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    suggested_stop: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    suggested_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    metadata_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[ScanResultStatus] = mapped_column(
        enum_col(ScanResultStatus, "scan_result_status"),
        default=ScanResultStatus.NEW,
        nullable=False,
    )
    promoted_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True,
    )
    promoted_approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id"), nullable=True,
    )
