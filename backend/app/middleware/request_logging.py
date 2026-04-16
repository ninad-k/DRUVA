from __future__ import annotations

import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.logging import get_logger
from app.infrastructure.metrics import http_request_duration_seconds, http_requests_total

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        status = str(response.status_code)
        http_requests_total.labels(method=request.method, route=path, status=status).inc()
        http_request_duration_seconds.labels(method=request.method, route=path).observe(duration)
        logger.info(
            "http.request",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration * 1000, 3),
        )
        return response
