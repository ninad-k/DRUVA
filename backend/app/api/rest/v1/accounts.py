"""Broker account CRUD endpoints.

Credentials are encrypted at rest with AES-256-GCM keyed by
``DHRUVA_MASTER_KEY`` (same pattern as webhook tokens). Plaintext never
touches the database — decryption happens only at broker-call time inside
:mod:`app.brokers.factory`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.dependencies import get_current_user
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.encryption import encrypt

router = APIRouter()


BrokerId = Literal[
    "zerodha",
    "upstox",
    "dhan",
    "fyers",
    "five_paisa",
    "alice_blue",
    "angel_one",
    "kotak_neo",
    "shoonya",
    "paper",
]


class AccountCreate(BaseModel):
    broker: BrokerId
    display_name: str | None = None
    api_key: str = Field(..., min_length=1)
    api_secret: str = Field(..., min_length=1)
    is_paper: bool = True


def _label_for_broker(broker: str) -> str:
    return " ".join(part.capitalize() for part in broker.split("_"))


def _to_dict(account: Account) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "broker": account.broker_id,
        # account_ref doubles as the user-visible display name (no separate
        # column on the model yet — a real broker_ref is only known after the
        # first authenticated call to the broker).
        "display_name": account.account_ref,
        "is_paper": account.is_paper,
        "is_connected": account.is_active and account.health_disabled_at is None,
        "created_at": _iso(account.created_at),
    }


def _iso(value: datetime) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _encrypt_or_400(plaintext: str, master_key_b64: str) -> tuple[str, str]:
    try:
        blob = encrypt(plaintext, master_key_b64=master_key_b64)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Server cannot encrypt broker credentials: DHRUVA_MASTER_KEY is "
                "missing or invalid. Generate one with "
                "`python -c \"import base64,os; print(base64.b64encode(os.urandom(32)).decode())\"` "
                "and set it in backend/.env."
            ),
        ) from exc
    return blob.ciphertext_b64, blob.nonce_b64


@router.get("")
async def list_accounts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Account)
            .where(Account.user_id == user.id)
            .order_by(Account.created_at.asc())
        )
    ).scalars().all()
    return [_to_dict(row) for row in rows]


@router.post("", status_code=201)
async def create_account(
    payload: AccountCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    settings = get_settings()
    key_ct, key_nonce = _encrypt_or_400(payload.api_key, settings.master_key)
    secret_ct, secret_nonce = _encrypt_or_400(payload.api_secret, settings.master_key)

    display_name = (payload.display_name or "").strip() or _label_for_broker(payload.broker)

    account = Account(
        user_id=user.id,
        broker_id=payload.broker,
        account_ref=display_name,
        api_key_encrypted=key_ct,
        api_key_nonce=key_nonce,
        api_secret_encrypted=secret_ct,
        api_secret_nonce=secret_nonce,
        is_active=True,
        is_paper=payload.is_paper,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _to_dict(account)
