from __future__ import annotations

import jwt
import pytest

from app.config import get_settings
from app.core.auth.tokens import TokenService
from app.core.errors import UnauthorizedError


@pytest.mark.unit
def test_access_token_round_trip() -> None:
    svc = TokenService()
    token = svc.create_access_token("user-1")
    assert svc.decode_access_token(token) == "user-1"


@pytest.mark.unit
def test_access_token_expiry_rejected() -> None:
    settings = get_settings()
    payload = {
        "sub": "user-1",
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": 1,
        "exp": 1,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(UnauthorizedError):
        TokenService().decode_access_token(token)


@pytest.mark.unit
def test_access_token_audience_rejected() -> None:
    settings = get_settings()
    payload = {
        "sub": "user-1",
        "iss": settings.jwt_issuer,
        "aud": "wrong",
        "iat": 9999999999,
        "exp": 99999999999,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(UnauthorizedError):
        TokenService().decode_access_token(token)
