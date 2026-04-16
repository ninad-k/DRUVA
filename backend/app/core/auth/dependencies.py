from __future__ import annotations

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.password import PasswordService
from app.core.auth.service import AuthService
from app.core.auth.tokens import TokenService
from app.db.models.user import User
from app.db.session import get_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_password_service() -> PasswordService:
    return PasswordService()


def get_token_service() -> TokenService:
    return TokenService()


def get_auth_service(
    session: AsyncSession = Depends(get_session),
    password_service: PasswordService = Depends(get_password_service),
    token_service: TokenService = Depends(get_token_service),
) -> AuthService:
    return AuthService(session=session, password_service=password_service, token_service=token_service)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
    token_service: TokenService = Depends(get_token_service),
) -> User:
    user_id = token_service.decode_access_token(token)
    return await AuthService(
        session=session,
        password_service=PasswordService(),
        token_service=token_service,
    ).get_current_user(user_id)
