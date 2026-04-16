"""Extra webhook receivers — AmiBroker, MetaTrader (MT4/MT5), GoCharting, N8N.

Each one looks up its WebhookSource by HMAC token (same pattern as ChartInk
and TradingView in webhooks.py), parses the source-specific payload, and
dispatches a Signal through the StrategyExecutor.

These extend the existing WebhookSource table — no new schema needed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_approval_service, get_execution_service
from app.config import get_settings
from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.strategy.executor import StrategyExecutor
from app.db.models.strategy import Strategy
from app.db.models.webhook import WebhookEvent, WebhookSource
from app.db.session import get_session
from app.infrastructure.logging import get_logger
from app.infrastructure.secret_tokens import hash_token
from app.strategies.base import Signal

logger = get_logger(__name__)

router_amibroker = APIRouter()
router_metatrader = APIRouter()
router_gocharting = APIRouter()
router_n8n = APIRouter()


async def _resolve(session: AsyncSession, token: str, kind: str) -> WebhookSource:
    settings = get_settings()
    digest = hash_token(token, master_key_b64=settings.master_key)
    row = await session.scalar(
        select(WebhookSource).where(
            WebhookSource.secret_token_hash == digest,
            WebhookSource.source == kind,
            WebhookSource.is_active.is_(True),
        )
    )
    if row is None:
        logger.warning("webhook.invalid_token", kind=kind)
        raise HTTPException(404, "invalid_webhook_token")
    return row


async def _dispatch(
    session: AsyncSession,
    source: WebhookSource,
    signal: Signal,
    execution: ExecutionService,
    approval: ApprovalService,
    payload: dict,
) -> dict:
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

    executor = StrategyExecutor(
        session=session, execution_service=execution, approval_service=approval
    )
    await executor.execute_signal_directly(strategy, signal)

    event.status = "processed"
    event.processed_at = datetime.now(UTC)
    await session.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# AmiBroker — typically posts an AFL-generated text/JSON body. We accept the
# canonical {symbol, action, quantity, price} shape; users wire the rest in
# their AFL `EnableScript` block.
# ---------------------------------------------------------------------------


@router_amibroker.post("/{secret_token}")
async def amibroker(
    secret_token: str,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    execution: ExecutionService = Depends(get_execution_service),
    approval: ApprovalService = Depends(get_approval_service),
) -> dict:
    source = await _resolve(session, secret_token, "amibroker")
    side_raw = str(payload.get("action", source.default_side)).upper()
    side = "SELL" if side_raw in {"SELL", "SHORT", "EXIT_LONG"} else "BUY"
    signal = Signal(
        symbol=str(payload.get("symbol", "")).upper(),
        side=side,
        quantity=Decimal(str(payload.get("quantity", source.default_quantity))),
        limit_price=_decimal_or_none(payload.get("price")),
        metadata={
            "exchange": str(payload.get("exchange", "NSE")),
            "amibroker_alert_id": payload.get("alert_id"),
        },
    )
    return await _dispatch(session, source, signal, execution, approval, payload)


# ---------------------------------------------------------------------------
# MetaTrader (MT4/MT5) — sends EA-generated alerts. Payloads vary; accept
# {ticket, symbol, type, lots, price, sl, tp}.
# ---------------------------------------------------------------------------


@router_metatrader.post("/{secret_token}")
async def metatrader(
    secret_token: str,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    execution: ExecutionService = Depends(get_execution_service),
    approval: ApprovalService = Depends(get_approval_service),
) -> dict:
    source = await _resolve(session, secret_token, "metatrader")
    type_code = str(payload.get("type", "BUY")).upper()
    side = "SELL" if type_code.startswith("SELL") else "BUY"
    # MT uses lots; convert if user supplied a lots->qty multiplier on the source.
    lots = Decimal(str(payload.get("lots", payload.get("quantity", source.default_quantity))))
    multiplier = Decimal(str(payload.get("contract_size", 1)))
    signal = Signal(
        symbol=str(payload.get("symbol", "")).upper(),
        side=side,
        quantity=lots * multiplier,
        limit_price=_decimal_or_none(payload.get("price")),
        stop_loss=_decimal_or_none(payload.get("sl")),
        take_profit=_decimal_or_none(payload.get("tp")),
        metadata={
            "exchange": str(payload.get("exchange", "NSE")),
            "mt_ticket": payload.get("ticket"),
        },
    )
    return await _dispatch(session, source, signal, execution, approval, payload)


# ---------------------------------------------------------------------------
# GoCharting — same canonical shape as TradingView so we accept either form.
# ---------------------------------------------------------------------------


@router_gocharting.post("/{secret_token}")
async def gocharting(
    secret_token: str,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    execution: ExecutionService = Depends(get_execution_service),
    approval: ApprovalService = Depends(get_approval_service),
) -> dict:
    source = await _resolve(session, secret_token, "gocharting")
    side = "SELL" if str(payload.get("action", source.default_side)).upper() == "SELL" else "BUY"
    signal = Signal(
        symbol=str(payload.get("symbol", "")).upper(),
        side=side,
        quantity=Decimal(str(payload.get("quantity", source.default_quantity))),
        limit_price=_decimal_or_none(payload.get("price")),
        metadata={"exchange": str(payload.get("exchange", "NSE"))},
    )
    return await _dispatch(session, source, signal, execution, approval, payload)


# ---------------------------------------------------------------------------
# N8N — accepts the canonical TradingView shape. N8N users typically build a
# workflow that POSTs JSON in this format from any upstream node.
# ---------------------------------------------------------------------------


@router_n8n.post("/{secret_token}")
async def n8n(
    secret_token: str,
    payload: dict,
    session: AsyncSession = Depends(get_session),
    execution: ExecutionService = Depends(get_execution_service),
    approval: ApprovalService = Depends(get_approval_service),
) -> dict:
    source = await _resolve(session, secret_token, "n8n")
    side = "SELL" if str(payload.get("action", source.default_side)).upper() == "SELL" else "BUY"
    signal = Signal(
        symbol=str(payload.get("symbol", "")).upper(),
        side=side,
        quantity=Decimal(str(payload.get("quantity", source.default_quantity))),
        limit_price=_decimal_or_none(payload.get("price")),
        metadata={
            "exchange": str(payload.get("exchange", "NSE")),
            "workflow_id": payload.get("workflow_id"),
            "execution_id": payload.get("execution_id"),
        },
    )
    return await _dispatch(session, source, signal, execution, approval, payload)


def _decimal_or_none(value) -> Decimal | None:
    if value in (None, "", 0, "0", "None"):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None
