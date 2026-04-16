"""HMAC token helpers — used for webhook secret-token lookup."""

from __future__ import annotations

import base64
import os

import pytest

from app.infrastructure.secret_tokens import generate_token, hash_token


@pytest.fixture
def master_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def test_generate_token_returns_unique_urlsafe_strings() -> None:
    a = generate_token()
    b = generate_token()
    assert a != b
    assert "/" not in a
    assert "+" not in a


def test_hash_token_is_deterministic_for_same_inputs(master_key: str) -> None:
    token = "supersecret"
    assert hash_token(token, master_key_b64=master_key) == hash_token(
        token, master_key_b64=master_key
    )


def test_hash_token_differs_per_master_key(master_key: str) -> None:
    other = base64.b64encode(os.urandom(32)).decode()
    token = "supersecret"
    assert hash_token(token, master_key_b64=master_key) != hash_token(
        token, master_key_b64=other
    )


def test_hash_token_differs_per_token(master_key: str) -> None:
    assert hash_token("a", master_key_b64=master_key) != hash_token("b", master_key_b64=master_key)
