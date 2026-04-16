from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.errors import DhruvaError
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = getattr(request.state, "correlation_id", None)
        try:
            return await call_next(request)
        except HTTPException:
            raise
        except DhruvaError as exc:
            logger.warning("dhruva.error", code=exc.code, message=str(exc))
            return JSONResponse(
                status_code=exc.http_status,
                content={
                    "error": exc.code,
                    "message": str(exc),
                    "correlation_id": correlation_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("dhruva.unhandled", message=str(exc), exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"error": "internal_error", "correlation_id": correlation_id},
            )
