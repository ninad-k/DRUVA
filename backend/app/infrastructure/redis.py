from __future__ import annotations

from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


async def get_redis() -> AsyncIterator[Redis]:
    global _redis  # noqa: PLW0603
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    yield _redis


async def close_redis() -> None:
    global _redis  # noqa: PLW0603
    if _redis is not None:
        await _redis.aclose()
        _redis = None
