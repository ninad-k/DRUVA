"""Fundamentals persistence model.

One row per ``(symbol, exchange, as_of_date)`` preserving history for
point-in-time backtests. Populated by the Screener.in scraper.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import JSON, Date, Index, Numeric, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import TimestampMixin


class FundamentalSnapshot(Base, TimestampMixin):
    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "exchange", "as_of_date", name="pk_fundamental_snapshot"),
        Index("ix_fundamentals_symbol_exchange", "symbol", "exchange"),
        Index("ix_fundamentals_sector", "sector"),
    )

    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, default="NSE")
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    roe: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    roce: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    sales_growth_3y: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    profit_growth_3y: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    promoter_holding: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="screener", nullable=False)
    raw_jsonb: Mapped[dict[str, object]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
