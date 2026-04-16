from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin, WebhookEventStatus, WebhookSourceType, enum_col


class WebhookSource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A registered external alert source (ChartInk / TradingView / GoCharting).

    Lookups go through ``secret_token_hash`` (HMAC-SHA256 of the token, keyed by
    the master secret) — O(1) DB hit, no per-request decryption, constant-time
    comparison. The encrypted blob is kept so the original token can be
    re-emitted to the user once at creation; it is never read at request time.
    """

    __tablename__ = "webhook_sources"
    __table_args__ = (
        Index("ix_webhook_sources_secret_hash", "secret_token_hash", unique=True),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=True)
    source: Mapped[WebhookSourceType] = mapped_column(enum_col(WebhookSourceType, "webhook_source_type"), nullable=False)
    secret_token_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    secret_token_nonce: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    default_side: Mapped[str] = mapped_column(String(8), default="BUY", nullable=False)
    default_quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WebhookEvent(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "webhook_events"

    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("webhook_sources.id"), nullable=False, index=True)
    payload_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[WebhookEventStatus] = mapped_column(enum_col(WebhookEventStatus, "webhook_event_status"), default=WebhookEventStatus.PENDING, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
