"""Broker account CRUD + broker sync endpoint.

Credentials are encrypted at rest with AES-256-GCM keyed by
``DHRUVA_MASTER_KEY`` (same pattern as webhook tokens). Plaintext never
touches the database — decryption happens only at broker-call time inside
:mod:`app.brokers.factory`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_broker_factory
from app.brokers.factory import BrokerFactory
from app.config import get_settings
from app.core.auth.dependencies import get_current_user
from app.core.errors import BrokerError
from app.db.models.account import Account
from app.db.models.common import Exchange, ProductType
from app.db.models.position import Position
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.encryption import encrypt
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

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

    # Paper accounts get their starting capital up front so the dashboard
    # has something honest to display before any trades fill. Live accounts
    # start at 0 — the next /sync call writes real cash from the broker.
    starting_capital = Decimal("1000000")
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
        paper_starting_capital=starting_capital,
        cash_balance=starting_capital if payload.is_paper else Decimal("0"),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _to_dict(account)


@router.post("/{account_id}/sync")
async def sync_account(
    account_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    factory: BrokerFactory = Depends(get_broker_factory),
) -> dict[str, Any]:
    """Pull current positions from the broker and upsert into the local DB.

    Paper accounts: no-op (paper trades are already written through the
    execution service when orders are placed). Live accounts: attempts a real
    broker call. Returns a 501 if the broker adapter's OAuth handshake is not
    yet wired — most adapters need an ``access_token`` in ``creds.extra`` that
    only an OAuth redirect flow can produce.
    """
    account = await session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="account_not_found")

    positions_count = (
        await session.execute(select(Position).where(Position.account_id == account.id))
    ).scalars().all()

    if account.is_paper:
        account.last_synced_at = datetime.now(UTC)
        await session.commit()
        return {
            "account_id": str(account.id),
            "synced": False,
            "reason": "Paper account — positions update automatically when paper orders fill.",
            "positions": len(positions_count),
            "orders": 0,
            "cash_balance": float(account.cash_balance),
        }

    try:
        adapter = await factory.create(account)
        broker_positions = await adapter.get_positions()
        margin = await adapter.get_margin()
    except BrokerError as exc:
        raise HTTPException(
            status_code=501,
            detail=(
                f"Broker sync not yet available for '{account.broker_id}': {exc}. "
                "This adapter needs an OAuth handshake (access_token) before it can "
                "fetch positions; that flow has not been wired in the UI yet."
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("account_sync_failed", account_id=str(account.id))
        raise HTTPException(status_code=502, detail=f"broker_sync_failed: {exc}") from exc

    upserted = 0
    for bp in broker_positions:
        try:
            exchange = Exchange(bp.exchange)
            product = ProductType(bp.product)
        except ValueError:
            logger.warning(
                "sync.skip_position",
                symbol=bp.symbol,
                exchange=bp.exchange,
                product=bp.product,
            )
            continue
        stmt = pg_insert(Position).values(
            account_id=account.id,
            symbol=bp.symbol,
            exchange=exchange,
            product=product,
            quantity=Decimal(str(bp.quantity)),
            avg_cost=Decimal(str(bp.average_price)),
            realized_pnl=Decimal(str(bp.pnl)),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_position_symbol",
            set_={
                "quantity": stmt.excluded.quantity,
                "avg_cost": stmt.excluded.avg_cost,
                "realized_pnl": stmt.excluded.realized_pnl,
            },
        )
        await session.execute(stmt)
        upserted += 1

    account.cash_balance = Decimal(str(margin.available_cash))
    account.last_synced_at = datetime.now(UTC)
    await session.commit()

    return {
        "account_id": str(account.id),
        "synced": True,
        "positions": upserted,
        "orders": 0,
        "cash_balance": float(account.cash_balance),
    }
