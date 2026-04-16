from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.auth.tokens import TokenService
from app.infrastructure.logging import bind_request_context


class AuthContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):  # type: ignore[no-untyped-def]
        super().__init__(app)
        self._tokens = TokenService()

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ").strip()
            try:
                user_id = self._tokens.decode_access_token(token)
                request.state.user_id = user_id
                bind_request_context(user_id=user_id)
            except Exception:  # noqa: BLE001
                pass
        return await call_next(request)
