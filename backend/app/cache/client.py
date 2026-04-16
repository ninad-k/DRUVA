from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis


class CacheClient:
    def __init__(self, redis: Redis):
        self._redis = redis

    async def get_json(self, key: str) -> Any | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def set_json(self, key: str, value: Any, ttl: int) -> None:
        await self._redis.set(key, json.dumps(value, default=str), ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[Any]], ttl: int) -> Any:
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        value = await factory()
        await self.set_json(key, value, ttl)
        return value

    async def invalidate_pattern(self, pattern: str) -> int:
        total = 0
        async for key in self._redis.scan_iter(match=pattern):
            total += await self._redis.delete(key)
        return total
