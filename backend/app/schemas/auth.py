from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)
    display_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str

    @model_validator(mode="after")
    def require_identifier(self) -> "LoginRequest":
        if not self.username and not self.email:
            raise ValueError("username_or_email_required")
        return self


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str | None = None
    email: EmailStr
    display_name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
