"""Goal-based SIP/STP models.

- ``investment_goals`` — named goals with target amount/date, monthly SIP, arbitrage buffer.
- ``sip_schedules``    — cadence rows (one per goal) tracking next-run date.
- ``sip_executions``   — per-execution log (one row each time a tranche fires).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class GoalStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SipExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestmentGoal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "investment_goals"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    current_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False,
    )
    monthly_sip_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False,
    )
    arbitrage_buffer_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0"), nullable=False,
    )
    equity_allocation_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("80"), nullable=False,
    )
    status: Mapped[GoalStatus] = mapped_column(
        enum_col(GoalStatus, "investment_goal_status"),
        default=GoalStatus.ACTIVE,
        nullable=False,
    )
    target_symbols: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class SipSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sip_schedules"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investment_goals.id", ondelete="CASCADE"), nullable=False,
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True,
    )
    day_of_month: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_run_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Number of STP tranches remaining when draining the arbitrage buffer.
    stp_tranches_remaining: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amount_per_tranche: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), nullable=False,
    )


class SipExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sip_executions"

    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investment_goals.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sip_schedules.id"), nullable=True,
    )
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, default="NSE")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id"), nullable=True,
    )
    status: Mapped[SipExecutionStatus] = mapped_column(
        enum_col(SipExecutionStatus, "sip_execution_status"),
        default=SipExecutionStatus.PENDING,
        nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
