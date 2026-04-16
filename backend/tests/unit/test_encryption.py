from __future__ import annotations

import base64

import pytest

from app.infrastructure.encryption import EncryptedBlob, decrypt, encrypt


def _master_key() -> str:
    return base64.b64encode(b"a" * 32).decode("ascii")


@pytest.mark.unit
def test_encrypt_decrypt_round_trip() -> None:
    blob = encrypt("secret", master_key_b64=_master_key())
    plaintext = decrypt(blob, master_key_b64=_master_key())
    assert plaintext == "secret"


@pytest.mark.unit
def test_decrypt_wrong_key_fails() -> None:
    blob = encrypt("secret", master_key_b64=_master_key())
    bad = base64.b64encode(b"b" * 32).decode("ascii")
    with pytest.raises(Exception):  # noqa: B017
        decrypt(blob, master_key_b64=bad)


@pytest.mark.unit
def test_tampered_ciphertext_fails() -> None:
    blob = encrypt("secret", master_key_b64=_master_key())
    tampered = EncryptedBlob(ciphertext_b64=blob.ciphertext_b64[:-2] + "AA", nonce_b64=blob.nonce_b64)
    with pytest.raises(Exception):  # noqa: B017
        decrypt(tampered, master_key_b64=_master_key())
