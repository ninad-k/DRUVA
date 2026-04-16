"""AES-256-GCM helpers for broker credential encryption at rest.

The master key comes from ``DHRUVA_MASTER_KEY`` (base64-encoded 32 bytes). Each
ciphertext is stored alongside its 12-byte nonce. **Never log plaintext
credentials** — decrypt only at the moment of use and drop the plaintext
immediately afterwards.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EncryptedBlob:
    """An AES-GCM ciphertext + its 12-byte nonce, both base64-encoded."""

    ciphertext_b64: str
    nonce_b64: str


def _load_key(master_key_b64: str) -> bytes:
    key = base64.b64decode(master_key_b64)
    if len(key) != 32:
        raise ValueError("DHRUVA_MASTER_KEY must decode to 32 bytes (256 bits).")
    return key


def encrypt(plaintext: str, *, master_key_b64: str) -> EncryptedBlob:
    """Encrypt ``plaintext`` with AES-256-GCM and a fresh nonce."""
    key = _load_key(master_key_b64)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return EncryptedBlob(
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        nonce_b64=base64.b64encode(nonce).decode("ascii"),
    )


def decrypt(blob: EncryptedBlob, *, master_key_b64: str) -> str:
    """Decrypt an :class:`EncryptedBlob` back to plaintext."""
    key = _load_key(master_key_b64)
    nonce = base64.b64decode(blob.nonce_b64)
    ciphertext = base64.b64decode(blob.ciphertext_b64)
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    return plaintext.decode("utf-8")
