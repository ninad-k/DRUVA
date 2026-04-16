"""Webhook receivers for ChartInk and TradingView, plus webhook-source CRUD
and Telegram notification linking.

Token resolution uses HMAC-SHA256 (keyed by the master secret) so a single
indexed lookup answers "is this token valid?" — no per-request decryption,
no linear scan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_approval_service, get_execution_service
from app.config import get_settings
from app.core.auth.dependencies import get_current_user
from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.strategy.executor import StrategyExecutor
from app.db.models.notification import NotificationConfig
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.models.webhook import WebhookEvent, WebhookSource
from app.db.session import get_session
from app.infrastructure.encryption import encrypt
from app.infrastructure.logging import get_logger
from app.infrastructure.secret_tokens import generate_token, hash_token
from app.strategies.base import Signal

logger = get_logger(__name__)

router_sources = APIRouter()
router_chartink = APIRouter()
router_tradingview = APIRouter()
router_notifications = APIRouter()


class WebhookSourcePayload(BaseModel):
    account_id: UUID
    source: Literal["chartink", "tradingview", "gocharting"]
    strategy_id: UUID
    default_side: Literal["BUY", "SELL"] = "BUY"
    default_quantity: int = 1


class TelegramPayload(BaseModel):
    chat_id: str


# ----------------------------------------------------------------------------
# Webhook source management
# ----------------------------------------------------------------------------


@router_sources.post("", status_code=201)
async def create_source(
    payload: WebhookSourcePayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Create a webhook source. The raw token is returned ONCE; we then store
    only its HMAC hash (for fast lookup) plus the encrypted blob (for completeness).
    """
    settings = get_settings()
    raw_token = generate_token()
    blob = encrypt(raw_token, master_key_b64=settings.master_key)
    token_hash = hash_token(raw_token, master_key_b64=settings.master_key)
    source = WebhookSource(
        account_id=payload.account_id,
        strategy_id=payload.strategy_id,
        source=payload.source,
        secret_token_encrypted=blob.ciphertext_b64,
        secret_token_nonce=blob.nonce_b64,
        secret_token_hash=token_hash,
        default_side=payload.default_side,
        default_quantity=payload.default_quantity,
        is_active=True,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return {"id": str(source.id), "secret_token": raw_token}


@router_sources.get("")
async def list_sources(
    account_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.execute(select(WebhookSource).where(WebhookSource.account_id == account_id))
    ).scalars().all()
    return [
        {
            "id": str(row.id),
            "account_id": str(row.account_id),
            "source": str(row.source),
            "default_side": row.default_side,
            "default_quantity": row.default_quantity,
            "is_active": row.is_active,
        }
        for row in rows
    ]


@router_sources.delete("/{source_id}")
async def delete_source(
    source_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    row = await session.get(WebhookSource, source_id)
    if row is None:
        raise HTTPException(404, "not_found")
    row.is_active = False
    await session.commit()
    return {"status": "revoked"}


@router_sources.get("/events")
async def list_events(
    source_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.execute(select(WebhookEvent).where(WebhookEvent.source_id == source_id))
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "status": str(r.status),
            "received_at": r.received_at.isoformat(),
        }
        for r in rows
    ]


# ----------------------------------------------------------------------------
# Inbound webhooks
# ----------------------------------------------------------------------------


@router_chartink.post("/{secret_token}")
async def chartink(
    secret_token: str,
    payload: dict[str, object],
    session: AsyncSession = Depends(get_session),
    execution_service: ExecutionService = Depends(get_execution_service),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> dict[str, object]:
    """ChartInk pushes a comma-separated stocks/trigger_prices payload."""
    source = await _resolve_source(session, secret_token, "chartink")
    event = WebhookEvent(
        source_id=source.id,
        payload_jsonb=payload,
        received_at=datetime.now(UTC),
        status="pending",
    )
    session.add(event)
    await session.flush()

    strategy = await session.get(Strategy, source.strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy_not_found")

    stocks = [s.strip() for s in str(payload.get("stocks", "")).split(",") if s.strip()]
    prices = str(payload.get("trigger_prices", "")).split(",")

    executor = StrategyExecutor(
        session=session,
        execution_service=execution_service,
        approval_service=approval_service,
    )
    for idx, stock in enumerate(stocks):
        price = Decimal(prices[idx]) if idx < len(prices) and prices[idx].strip() else Decimal("0")
        signal = Signal(
            symbol=stock,
            side=source.default_side,  # configured per source — supports SELL scans too
            quantity=Decimal(source.default_quantity),
            limit_price=price,
            metadata={"exchange": "NSE", "scan_name": payload.get("scan_name")},
        )
        await executor.execute_signal_directly(strategy, signal)

    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok", "signals": len(stocks)}


@router_tradingview.post("/{secret_token}")
async def tradingview(
    secret_token: str,
    payload: dict[str, object],
    session: AsyncSession = Depends(get_session),
    execution_service: ExecutionService = Depends(get_execution_service),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> dict[str, object]:
    """TradingView posts free-form JSON; we accept the canonical shape
    {action, symbol, exchange, quantity, price, comment}."""
    source = await _resolve_source(session, secret_token, "tradingview")
    event = WebhookEvent(
        source_id=source.id,
        payload_jsonb=payload,
        received_at=datetime.now(UTC),
        status="pending",
    )
    session.add(event)
    await session.flush()

    strategy = await session.get(Strategy, source.strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy_not_found")

    action = str(payload.get("action", source.default_side)).upper()
    side = "SELL" if action == "SELL" else "BUY"
    qty = payload.get("quantity", source.default_quantity)
    price_raw = payload.get("price", 0)

    signal = Signal(
        symbol=str(payload.get("symbol", "")),
        side=side,
        quantity=Decimal(str(qty)),
        limit_price=Decimal(str(price_raw)) if str(price_raw) not in {"", "0", "None"} else None,
        metadata={
            "exchange": str(payload.get("exchange", "NSE")),
            "comment": str(payload.get("comment", "")),
        },
    )
    executor = StrategyExecutor(
        session=session,
        execution_service=execution_service,
        approval_service=approval_service,
    )
    await executor.execute_signal_directly(strategy, signal)

    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok"}


# ----------------------------------------------------------------------------
# Telegram link / unlink
# ----------------------------------------------------------------------------


@router_notifications.post("/telegram", status_code=201)
async def link_telegram(
    payload: TelegramPayload,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    cfg = NotificationConfig(user_id=user.id, channel="telegram", destination=payload.chat_id)
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return {"id": str(cfg.id), "chat_id": cfg.destination}


@router_notifications.get("")
async def list_notifications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    rows = (
        await session.execute(
            select(NotificationConfig).where(
                NotificationConfig.user_id == user.id,
                NotificationConfig.is_active.is_(True),
            )
        )
    ).scalars().all()
    return [
        {"id": str(row.id), "channel": row.channel, "destination": row.destination}
        for row in rows
    ]


@router_notifications.delete("/{config_id}")
async def unlink_notification(
    config_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    row = await session.get(NotificationConfig, config_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "not_found")
    row.is_active = False
    await session.commit()
    return {"status": "deleted"}


# ----------------------------------------------------------------------------
# Internal
# ----------------------------------------------------------------------------


async def _resolve_source(
    session: AsyncSession,
    token: str,
    source_kind: str,
) -> WebhookSource:
    """Look up an active source by HMAC of the supplied token (constant-time)."""
    settings = get_settings()
    digest = hash_token(token, master_key_b64=settings.master_key)
    row = await session.scalar(
        select(WebhookSource).where(
            WebhookSource.secret_token_hash == digest,
            WebhookSource.source == source_kind,
            WebhookSource.is_active.is_(True),
        )
    )
    if row is None:
        # Don't leak why — never echo "wrong source kind" vs "wrong token".
        logger.warning("webhook.invalid_token", source_kind=source_kind)
        raise HTTPException(404, "invalid_webhook_token")
    return row
