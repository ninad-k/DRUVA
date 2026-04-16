from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import ApprovalStatus, UUIDPrimaryKeyMixin, enum_col


class ApprovalRequest(Base, UUIDPrimaryKeyMixin):
    """Action-Center approval row.

    When a strategy with ``requires_approval=True`` emits a signal, the
    ExecutionService creates an Order in status ``pending_approval`` AND a
    matching ApprovalRequest. The two are linked via ``order_id`` so the
    ApprovalService can find and update the right Order on approve/reject.
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_account_status_requested", "account_id", "status", "requested_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    signal_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(enum_col(ApprovalStatus, "approval_status"), default=ApprovalStatus.PENDING, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
