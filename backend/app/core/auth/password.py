from __future__ import annotations

from passlib.hash import argon2


class PasswordService:
    def hash(self, plaintext: str) -> str:
        return argon2.using(type="ID").hash(plaintext)

    def verify(self, plaintext: str, hashed: str) -> bool:
        try:
            return bool(argon2.verify(plaintext, hashed))
        except Exception:  # noqa: BLE001
            return False
