"""HMAC-based secret-token helpers.

We never persist webhook tokens in plaintext, but we also never want to decrypt
them on every request just to compare. The compromise: store an HMAC-SHA256 of
the token (keyed by the master secret) and look it up by hash. Constant-time
comparison happens implicitly because an exact equality match in SQL is fine
when both sides are uniform-length hex digests.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


def generate_token(num_bytes: int = 24) -> str:
    """Return a fresh URL-safe token (raw, given once to the user)."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str, *, master_key_b64: str) -> str:
    """Return the keyed HMAC-SHA256 hex digest of ``token``.

    The same ``master_key_b64`` used for AES-GCM credential encryption keys this
    HMAC, so leaking the DB row alone doesn't reveal the token.
    """
    key = base64.b64decode(master_key_b64)
    return hmac.new(key, token.encode("utf-8"), hashlib.sha256).hexdigest()
