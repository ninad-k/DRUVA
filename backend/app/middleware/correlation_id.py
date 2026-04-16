from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from opentelemetry.trace import get_current_span
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.logging import bind_request_context


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = request.headers.get("X-Correlation-Id", str(uuid4()))
        trace_id = f"{get_current_span().get_span_context().trace_id:032x}"
        request.state.correlation_id = correlation_id
        bind_request_context(correlation_id=correlation_id, trace_id=trace_id)
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response
