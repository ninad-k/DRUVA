from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class NotificationConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_configs"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)


class RiskAlert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "risk_alerts"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    is_cleared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
