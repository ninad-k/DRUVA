from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from app.core.errors import UnauthorizedError


class TokenService:
    def __init__(self) -> None:
        self._settings = get_settings()

    def create_access_token(self, user_id: str) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": user_id,
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "iat": now,
            "exp": now + timedelta(seconds=self._settings.jwt_access_ttl_seconds),
        }
        return jwt.encode(payload, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm)

    def create_refresh_token(self) -> tuple[str, str]:
        raw = secrets.token_urlsafe(48)
        hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return raw, hashed

    def decode_access_token(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=[self._settings.jwt_algorithm],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("invalid_or_expired_token") from exc

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedError("token_missing_sub")
        return str(user_id)
