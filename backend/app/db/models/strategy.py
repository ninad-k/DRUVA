from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import StrategyMode, TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class Strategy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "strategies"

    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_class: Mapped[str] = mapped_column(String(255), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    mode: Mapped[StrategyMode] = mapped_column(enum_col(StrategyMode, "strategy_mode"), default=StrategyMode.PAPER, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_ml: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
