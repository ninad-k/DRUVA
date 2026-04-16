from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.cache import keys
from app.infrastructure.redis import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        user_id = getattr(request.state, "user_id", None)
        account_id = request.query_params.get("account_id")

        redis: Redis | None = None
        async for client in get_redis():
            redis = client
            break

        if redis and user_id:
            ok, retry = await _check_limit(redis, keys.ratelimit_user(str(user_id)), 100, 60)
            if not ok:
                return _limited(retry)

        if redis and request.url.path == "/api/v1/orders" and request.method == "POST" and account_id:
            ok, retry = await _check_limit(redis, keys.ratelimit_orders(account_id), 20, 60)
            if not ok:
                return _limited(retry)

        return await call_next(request)


async def _check_limit(redis: Redis, key: str, limit: int, window_secs: int) -> tuple[bool, int]:
    now = int(time.time())
    bucket = f"{key}:{now // window_secs}"
    count = await redis.incr(bucket)
    if count == 1:
        await redis.expire(bucket, window_secs)
    if count > limit:
        ttl = await redis.ttl(bucket)
        return False, max(ttl, 1)
    return True, 0


def _limited(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(retry_after)},
        content={"error": "rate_limited", "retry_after_seconds": retry_after},
    )
