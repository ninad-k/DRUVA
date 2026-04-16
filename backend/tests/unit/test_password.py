from __future__ import annotations

import pytest

from app.core.auth.password import PasswordService


@pytest.mark.unit
def test_hash_verify_success() -> None:
    service = PasswordService()
    hashed = service.hash("Passw0rd!")
    assert service.verify("Passw0rd!", hashed)


@pytest.mark.unit
def test_wrong_password_fails() -> None:
    service = PasswordService()
    hashed = service.hash("Passw0rd!")
    assert not service.verify("wrong", hashed)


@pytest.mark.unit
def test_tampered_hash_fails() -> None:
    service = PasswordService()
    hashed = service.hash("Passw0rd!")
    assert not service.verify("Passw0rd!", hashed + "tampered")
