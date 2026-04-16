from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.password import PasswordService
from app.core.auth.tokens import TokenService
from app.core.errors import NotFoundError, UnauthorizedError, ValidationError
from app.db.models.user import RefreshToken, User
from app.utils.time import utcnow


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


class AuthService:
    def __init__(
        self,
        session: AsyncSession,
        password_service: PasswordService,
        token_service: TokenService,
    ):
        self._session = session
        self._password = password_service
        self._tokens = token_service
        self._settings = get_settings()

    async def register(self, email: str, password: str, display_name: str) -> User:
        existing = await self._session.scalar(select(User).where(User.email == email.lower()))
        if existing:
            raise ValidationError("email_already_registered")
        user = User(
            email=email.lower(),
            password_hash=self._password.hash(password),
            display_name=display_name,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self._session.scalar(select(User).where(User.email == email.lower()))
        if not user or not self._password.verify(password, user.password_hash):
            raise UnauthorizedError("invalid_credentials")
        return await self._issue_token_pair(user.id)

    async def refresh(self, refresh_token: str) -> TokenPair:
        token_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        token = await self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked.is_(False),
            )
        )
        if token is None or token.expires_at <= utcnow():
            raise UnauthorizedError("invalid_refresh_token")

        pair = await self._issue_token_pair(token.user_id)
        new_hash = hashlib.sha256(pair.refresh_token.encode("utf-8")).hexdigest()
        new_token = await self._session.scalar(select(RefreshToken).where(RefreshToken.token_hash == new_hash))
        if new_token is None:
            raise UnauthorizedError("refresh_rotation_failed")
        token.is_revoked = True
        token.rotated_to_id = new_token.id
        await self._session.commit()
        return pair

    async def logout(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))
            .values(is_revoked=True)
        )
        await self._session.commit()

    async def get_current_user(self, user_id: str) -> User:
        try:
            uid = uuid.UUID(user_id)
        except ValueError as exc:
            raise UnauthorizedError("invalid_user_id") from exc
        user = await self._session.get(User, uid)
        if user is None:
            raise NotFoundError("user_not_found")
        return user

    async def _issue_token_pair(self, user_id: uuid.UUID) -> TokenPair:
        access = self._tokens.create_access_token(str(user_id))
        refresh_raw, refresh_hash = self._tokens.create_refresh_token()
        refresh = RefreshToken(
            user_id=user_id,
            token_hash=refresh_hash,
            expires_at=utcnow() + timedelta(seconds=self._settings.jwt_refresh_ttl_seconds),
        )
        self._session.add(refresh)
        await self._session.commit()
        return TokenPair(
            access_token=access,
            refresh_token=refresh_raw,
            expires_in=self._settings.jwt_access_ttl_seconds,
        )
