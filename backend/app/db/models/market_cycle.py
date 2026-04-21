"""Market cycle state.

One row per trading day. Captures Nifty50 / SmallCap100 ROC and the derived
regime used by the portfolio allocator to size positions.
"""

from __future__ import annotations

import enum
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin, enum_col


class MarketRegime(str, enum.Enum):
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"


class MarketCycleState(Base, TimestampMixin):
    __tablename__ = "market_cycle_state"

    as_of_date: Mapped[date] = mapped_column(Date, primary_key=True)
    regime: Mapped[MarketRegime] = mapped_column(
        enum_col(MarketRegime, "market_regime"), default=MarketRegime.NEUTRAL, nullable=False,
    )
    nifty_roc_18m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    smallcap_roc_20m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    breadth_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    suggested_allocation_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("60"), nullable=False,
    )
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
