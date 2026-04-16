"""Seed NSE / BSE market sessions and 2026 holidays.

Run once after `alembic upgrade head` so the RiskEngine's market-hours check
has data to work with. Idempotent — re-running upserts.

Sessions (regular equity):
  Mon-Fri 09:15 – 15:30 IST  (which is 03:45 – 10:00 UTC)

Holidays: official NSE 2026 calendar published at the start of FY 2026.
Update the ``HOLIDAYS_2026`` list yearly from
https://www.nseindia.com/resources/exchange-communication-holidays
"""

from __future__ import annotations

import asyncio
from datetime import date, time

from sqlalchemy import delete

from app.db.models.calendar import MarketHoliday, MarketSession
from app.db.models.common import Exchange, SessionType
from app.db.session import SessionLocal

# UTC times for IST 09:15-15:30 (IST = UTC+5:30)
SESSION_OPEN_UTC = time(3, 45)
SESSION_CLOSE_UTC = time(10, 0)
PRE_MARKET_OPEN_UTC = time(3, 30)
PRE_MARKET_CLOSE_UTC = time(3, 45)
POST_CLOSE_OPEN_UTC = time(10, 10)
POST_CLOSE_CLOSE_UTC = time(10, 30)

EXCHANGES = ["NSE", "BSE"]

# 2026 NSE holiday calendar (subject to NSE confirmation each year).
HOLIDAYS_2026: list[tuple[date, str]] = [
    (date(2026, 1, 26), "Republic Day"),
    (date(2026, 3, 4), "Holi"),
    (date(2026, 3, 19), "Mahashivratri"),
    (date(2026, 4, 3), "Good Friday"),
    (date(2026, 4, 14), "Dr. Ambedkar Jayanti"),
    (date(2026, 4, 21), "Mahavir Jayanti"),
    (date(2026, 5, 1), "Maharashtra Day"),
    (date(2026, 5, 26), "Buddha Purnima"),
    (date(2026, 6, 26), "Bakri Eid"),
    (date(2026, 8, 15), "Independence Day"),
    (date(2026, 8, 26), "Ganesh Chaturthi"),
    (date(2026, 10, 2), "Mahatma Gandhi Jayanti"),
    (date(2026, 10, 20), "Dussehra"),
    (date(2026, 11, 9), "Diwali Laxmi Pujan (Muhurat trading evening)"),
    (date(2026, 11, 10), "Diwali Balipratipada"),
    (date(2026, 12, 25), "Christmas"),
]


async def seed() -> None:
    async with SessionLocal() as session:
        # Wipe-and-rewrite is fine for a small reference table.
        await session.execute(delete(MarketSession))
        await session.execute(delete(MarketHoliday))

        for exchange in EXCHANGES:
            for weekday in range(0, 5):  # Monday=0 .. Friday=4
                session.add(
                    MarketSession(
                        exchange=Exchange(exchange),
                        weekday=weekday,
                        open_time=PRE_MARKET_OPEN_UTC,
                        close_time=PRE_MARKET_CLOSE_UTC,
                        session_type=SessionType.PRE,
                    )
                )
                session.add(
                    MarketSession(
                        exchange=Exchange(exchange),
                        weekday=weekday,
                        open_time=SESSION_OPEN_UTC,
                        close_time=SESSION_CLOSE_UTC,
                        session_type=SessionType.REGULAR,
                    )
                )
                session.add(
                    MarketSession(
                        exchange=Exchange(exchange),
                        weekday=weekday,
                        open_time=POST_CLOSE_OPEN_UTC,
                        close_time=POST_CLOSE_CLOSE_UTC,
                        session_type=SessionType.POST,
                    )
                )

            for h_date, description in HOLIDAYS_2026:
                session.add(
                    MarketHoliday(
                        exchange=Exchange(exchange),
                        holiday_date=h_date,
                        description=description,
                    )
                )

        await session.commit()
        print(
            f"Seeded {len(EXCHANGES) * 5 * 3} sessions and "
            f"{len(EXCHANGES) * len(HOLIDAYS_2026)} holiday rows."
        )


if __name__ == "__main__":
    asyncio.run(seed())
