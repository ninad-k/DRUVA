"""AI Advisor persistence models.

Four tables:
- ``advisor_llm_config`` — per-user LLM backend config (provider, model, url, key).
- ``advisor_watchlist`` — user-curated or auto-discovered symbols the advisor tracks.
- ``advisor_score``    — latest composite + component scores per symbol per run.
- ``advisor_run``      — metadata for a single scan (timestamp, macro regime, LLM used).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin, enum_col


class AdvisorLLMProvider(str, enum.Enum):
    NONE = "none"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class MacroRegime(str, enum.Enum):
    AGGRESSIVE = "aggressive"   # ROC near 0 — cycle bottom, deploy capital
    NEUTRAL = "neutral"
    DEFENSIVE = "defensive"     # ROC near top — reduce exposure


class AdvisorLLMConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advisor_llm_configs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True, index=True,
    )
    provider: Mapped[AdvisorLLMProvider] = mapped_column(
        enum_col(AdvisorLLMProvider, "advisor_llm_provider"),
        default=AdvisorLLMProvider.OLLAMA,
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(128), default="gemma3:4b", nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), default="http://localhost:11434", nullable=False)
    # Encrypted via app.infrastructure.encryption before persistence.
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("0.2"), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdvisorWatchlist(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advisor_watchlist"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "exchange", name="uq_advisor_watch_user_symbol"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE", nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AdvisorRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advisor_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True,
    )
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    macro_regime: Mapped[MacroRegime] = mapped_column(
        enum_col(MacroRegime, "advisor_macro_regime"), nullable=False,
    )
    nifty_roc: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    smallcap_roc: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbols_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AdvisorScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "advisor_scores"
    __table_args__ = (UniqueConstraint("run_id", "symbol", "exchange", name="uq_advisor_score_run_symbol"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("advisor_runs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="NSE", nullable=False)
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    fundamental_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    technical_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    momentum_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    llm_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    multibagger_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)  # S / A / B / C
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    suggested_allocation_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    features: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
