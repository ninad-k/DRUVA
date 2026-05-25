from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth.password import PasswordService
from app.db.models.user import User
from app.db.session import SessionLocal


ADMIN_USERNAME = os.getenv("DHRUVA_SEED_ADMIN_USERNAME", "administrator")
ADMIN_PASSWORD = os.getenv("DHRUVA_SEED_ADMIN_PASSWORD", "Admin@123")
ADMIN_EMAIL = os.getenv("DHRUVA_SEED_ADMIN_EMAIL", "administrator@dhruva.local")
ADMIN_DISPLAY_NAME = os.getenv("DHRUVA_SEED_ADMIN_DISPLAY_NAME", "Administrator")


async def main() -> None:
    password_service = PasswordService()
    username = ADMIN_USERNAME.lower()
    email = ADMIN_EMAIL.lower()

    async with SessionLocal() as session:
        user = await session.scalar(
            select(User).where((User.username == username) | (User.email == email))
        )
        if user is None:
            session.add(
                User(
                    username=username,
                    email=email,
                    display_name=ADMIN_DISPLAY_NAME,
                    password_hash=password_service.hash(ADMIN_PASSWORD),
                )
            )
            action = "created"
        else:
            user.username = username
            user.email = email
            user.display_name = ADMIN_DISPLAY_NAME
            user.password_hash = password_service.hash(ADMIN_PASSWORD)
            user.is_active = True
            action = "updated"

        await session.commit()
        print(f"Seed admin user {action}: username={username} email={email}")


if __name__ == "__main__":
    asyncio.run(main())
