from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.core.auth.dependencies import get_auth_service, get_current_user
from app.core.auth.service import AuthService
from app.db.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, service: AuthService = Depends(get_auth_service)) -> UserResponse:
    user = await service.register(payload.email, payload.password, payload.display_name)
    return UserResponse.model_validate(user, from_attributes=True)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    tokens = await service.login(payload.email, payload.password)
    return TokenResponse(**tokens.__dict__)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, service: AuthService = Depends(get_auth_service)) -> TokenResponse:
    tokens = await service.refresh(payload.refresh_token)
    return TokenResponse(**tokens.__dict__)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    service: AuthService = Depends(get_auth_service),
    user: User = Depends(get_current_user),
) -> Response:
    await service.logout(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user, from_attributes=True)
