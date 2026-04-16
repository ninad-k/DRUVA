"""FastAPI dependency factories.

Most callers should use the FastAPI ``Depends`` chain (``get_execution_service``,
``get_approval_service``, …). The ``build_execution_service_for_session``
helper exists for code paths that have already opened their own session
(scheduler jobs, the Telegram bot listener) and need to assemble the same
service stack without going through the request lifecycle.
"""

from __future__ import annotations

import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.factory import BrokerFactory
from app.cache.client import CacheClient
from app.config import Settings, get_settings
from app.core.audit.event_store import AuditService
from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.execution.position_tracker import PositionTracker
from app.core.execution.risk_engine import RiskEngine
from app.core.notifications.telegram import TelegramNotifier
from app.db.models.notification import NotificationConfig
from app.db.models.order import Order
from app.db.session import get_session
from app.infrastructure.http import get_http_client
from app.infrastructure.logging import get_logger
from app.infrastructure.redis import get_redis

logger = get_logger(__name__)


def get_cache_client(redis: Redis = Depends(get_redis)) -> CacheClient:
    return CacheClient(redis)


def get_broker_factory(
    http: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
    cache: CacheClient = Depends(get_cache_client),
) -> BrokerFactory:
    return BrokerFactory(http=http, settings=settings, cache=cache)


def get_telegram_notifier(request: Request) -> TelegramNotifier | None:
    """Resolved from app.state set in main.lifespan. None if not configured."""
    return getattr(request.app.state, "telegram_notifier", None)


def get_execution_service(
    session: AsyncSession = Depends(get_session),
    broker_factory: BrokerFactory = Depends(get_broker_factory),
    cache: CacheClient = Depends(get_cache_client),
    redis: Redis = Depends(get_redis),
    notifier: TelegramNotifier | None = Depends(get_telegram_notifier),
) -> ExecutionService:
    on_fill = _make_telegram_on_fill(session=session, notifier=notifier)
    return ExecutionService(
        session=session,
        broker_factory=broker_factory,
        audit_service=AuditService(),
        risk_engine=RiskEngine(session=session, redis=redis, broker_factory=broker_factory),
        position_tracker=PositionTracker(session=session, cache=cache),
        on_fill=on_fill,
    )


def get_approval_service(
    session: AsyncSession = Depends(get_session),
    execution_service: ExecutionService = Depends(get_execution_service),
) -> ApprovalService:
    return ApprovalService(session=session, execution_service=execution_service)


# ----------------------------------------------------------------------------
# Helpers used by background tasks (no FastAPI request available)
# ----------------------------------------------------------------------------


def build_execution_service_for_session(
    *,
    session: AsyncSession,
    http: httpx.AsyncClient,
    cache: CacheClient,
    redis: Redis,
    settings: Settings,
    notifier: TelegramNotifier | None,
) -> ExecutionService:
    """Build an ExecutionService bound to ``session`` for use by jobs/listeners."""
    broker_factory = BrokerFactory(http=http, settings=settings, cache=cache)
    on_fill = _make_telegram_on_fill(session=session, notifier=notifier) if notifier else None
    return ExecutionService(
        session=session,
        broker_factory=broker_factory,
        audit_service=AuditService(),
        risk_engine=RiskEngine(session=session, redis=redis, broker_factory=broker_factory),
        position_tracker=PositionTracker(session=session, cache=cache),
        on_fill=on_fill,
    )


def _make_telegram_on_fill(
    *,
    session: AsyncSession,
    notifier: TelegramNotifier | None,
):
    """Return a callable suitable for ``ExecutionService.on_fill``.

    Looks up every Telegram chat id linked to the order owner and pushes a
    formatted "order filled" message. Failures are swallowed and logged; the
    order is already persisted by the time we get here.
    """
    if notifier is None:
        return None

    async def _on_fill(order: Order) -> None:
        try:
            cfgs = (
                await session.execute(
                    select(NotificationConfig).where(
                        NotificationConfig.user_id == order.user_id,
                        NotificationConfig.channel == "telegram",
                        NotificationConfig.is_active.is_(True),
                    )
                )
            ).scalars().all()
            for cfg in cfgs:
                await notifier.send_order_filled(cfg.destination, order)
        except Exception as exc:  # noqa: BLE001
            logger.warning("execution.telegram_emit_failed", error=str(exc))

    return _on_fill
