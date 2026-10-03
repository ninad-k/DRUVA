"""Inbound WhatsApp (Twilio) webhook — approve/reject orders by replying.

Twilio POSTs a form body (``From``, ``Body``, …) for every reply. Requests are
authenticated with ``X-Twilio-Signature``; only numbers linked through
``POST /api/v1/notifications/whatsapp`` may approve or reject.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from urllib.parse import parse_qsl
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_approval_service
from app.config import get_settings
from app.core.auth.dependencies import get_current_user
from app.core.errors import DhruvaError
from app.core.execution.approval_service import ApprovalService
from app.db.models.notification import NotificationConfig
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()
router_link = APIRouter()

_COMMAND_RE = re.compile(r"^\s*(APPROVE|REJECT)\s+([0-9a-fA-F-]{36})\s*$", re.IGNORECASE)

_HELP_TEXT = "Reply APPROVE <approval_id> or REJECT <approval_id>."


class WhatsAppLinkPayload(BaseModel):
    number: str


def _normalize_number(raw: str) -> str:
    return raw.strip().removeprefix("whatsapp:").replace(" ", "")


def compute_twilio_signature(url: str, params: list[tuple[str, str]], auth_token: str) -> str:
    """HMAC-SHA1 of the URL followed by each POST param (sorted by key) as key+value."""
    payload = url + "".join(k + v for k, v in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def _public_url(request: Request) -> str:
    # Twilio signs the URL it called; behind a TLS-terminating proxy the
    # internal scheme/host differ, so prefer the forwarded values.
    proto = request.headers.get("x-forwarded-proto")
    host = request.headers.get("x-forwarded-host")
    if not proto and not host:
        return str(request.url)
    url = request.url.replace(scheme=proto or request.url.scheme)
    if host:
        url = url.replace(netloc=host)
    return str(url)


def _twiml(message: str) -> Response:
    body = f"<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response><Message>{escape(message)}</Message></Response>"
    return Response(content=body, media_type="application/xml")


@router.post("")
async def whatsapp_inbound(
    request: Request,
    session: AsyncSession = Depends(get_session),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> Response:
    settings = get_settings()
    if not settings.twilio_auth_token:
        logger.warning("whatsapp.webhook_rejected", reason="credentials_unset")
        raise HTTPException(status_code=403, detail="forbidden")

    raw = (await request.body()).decode("utf-8", errors="replace")
    params = parse_qsl(raw, keep_blank_values=True)
    expected = compute_twilio_signature(_public_url(request), params, settings.twilio_auth_token)
    provided = request.headers.get("x-twilio-signature", "")
    if not hmac.compare_digest(expected, provided):
        logger.warning("whatsapp.webhook_rejected", reason="bad_signature")
        raise HTTPException(status_code=403, detail="forbidden")

    form = dict(params)
    sender = _normalize_number(form.get("From", ""))
    cfg = None
    if sender:
        cfg = (
            await session.execute(
                select(NotificationConfig).where(
                    NotificationConfig.channel == "whatsapp",
                    NotificationConfig.destination == sender,
                    NotificationConfig.is_active.is_(True),
                )
            )
        ).scalars().first()
    if cfg is None:
        logger.warning("whatsapp.webhook_rejected", reason="unknown_sender")
        raise HTTPException(status_code=403, detail="forbidden")

    match = _COMMAND_RE.match(form.get("Body", ""))
    if match is None:
        return _twiml(_HELP_TEXT)
    action = match.group(1).upper()
    try:
        approval_id = UUID(match.group(2))
    except ValueError:
        return _twiml(_HELP_TEXT)

    try:
        if action == "APPROVE":
            await approval_service.approve(str(cfg.user_id), approval_id)
            return _twiml(f"Approved {approval_id}")
        await approval_service.reject(str(cfg.user_id), approval_id)
        return _twiml(f"Rejected {approval_id}")
    except DhruvaError as exc:
        return _twiml(f"Failed: {exc.code}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("whatsapp.webhook_action_failed", error=str(exc))
        return _twiml("Failed: internal_error")


@router_link.post("", status_code=201)
async def link_whatsapp(
    payload: WhatsAppLinkPayload,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    number = _normalize_number(payload.number)
    if not re.fullmatch(r"\+[1-9]\d{7,14}", number):
        raise HTTPException(status_code=422, detail="invalid_number")
    cfg = NotificationConfig(user_id=user.id, channel="whatsapp", destination=number)
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    return {"id": str(cfg.id), "number": cfg.destination}
