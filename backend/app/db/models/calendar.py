from __future__ import annotations

from datetime import date, time

from sqlalchemy import Date, Index, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import Exchange, SessionType, UUIDPrimaryKeyMixin, enum_col


class MarketHoliday(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "market_holidays"
    __table_args__ = (
        UniqueConstraint("exchange", "holiday_date", name="uq_holiday_exchange_date"),
        Index("ix_holiday_exchange_date", "exchange", "holiday_date"),
    )

    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_market_holiday"), nullable=False)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)


class MarketSession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "market_sessions"

    exchange: Mapped[Exchange] = mapped_column(enum_col(Exchange, "exchange_market_session"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    open_time: Mapped[time] = mapped_column(Time, nullable=False)
    close_time: Mapped[time] = mapped_column(Time, nullable=False)
    session_type: Mapped[SessionType] = mapped_column(enum_col(SessionType, "session_type"), nullable=False)
