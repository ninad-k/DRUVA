from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def check_db(session: AsyncSession) -> tuple[bool, str]:
    try:
        await session.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


async def check_redis(redis: Redis) -> tuple[bool, str]:
    try:
        pong = await redis.ping()
        return (bool(pong), "ok" if pong else "ping_failed")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
