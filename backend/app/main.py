from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rest.v1 import (
    advisor,
    approvals,
    auth,
    fundamentals,
    goals,
    instruments,
    market_cycle,
    options,
    orders,
    scan_results,
    scanners,
    strategies,
    watchlists,
    webhooks,
    webhooks_extra,
)
from app.brokers.factory import BrokerFactory
from app.cache.client import CacheClient
from app.config import get_settings
from app.core.execution.approval_service import ApprovalService
from app.core.notifications.telegram import TelegramBotListener, TelegramNotifier
from app.data.streaming import OhlcvWriter, StreamHub, StreamingManager
from app.db.session import SessionLocal, engine, get_session
from app.infrastructure.health import check_db, check_redis
from app.infrastructure.http import close_http_client, get_http_client
from app.infrastructure.jobs import register_jobs
from app.infrastructure.logging import configure_logging, get_logger
from app.infrastructure.redis import close_redis, get_redis
from app.infrastructure.scheduler import get_scheduler, start_scheduler, stop_scheduler
from app.infrastructure.tracing import configure_tracing
from app.middleware.auth_context import AuthContextMiddleware
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.core.scanner.registry import import_scanners
from app.strategies.registry import import_strategies

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("dhruva.startup", env=settings.env, version=settings.service_version)
    import_strategies()
    import_scanners()

    # ----- shared singletons exposed via lifespan attrs -------------------
    http = await _ensure_http_singleton()
    redis = await _ensure_redis_singleton()
    cache = CacheClient(redis)
    notifier = TelegramNotifier(bot_token=settings.telegram_bot_token, http=http)
    app.state.telegram_notifier = notifier
    app.state.cache = cache

    # ----- streaming bus (in-process pub/sub + OHLCV writer) -------------
    stream_hub = StreamHub()
    app.state.stream_hub = stream_hub
    ohlcv_writer = OhlcvWriter(hub=stream_hub, session_factory=SessionLocal)
    streaming_manager = StreamingManager(
        hub=stream_hub,
        factory=BrokerFactory(http=http, settings=settings, cache=cache),
        session_factory=SessionLocal,
    )
    streaming_tasks = [
        asyncio.create_task(ohlcv_writer.run(), name="ohlcv_writer"),
        asyncio.create_task(streaming_manager.run(), name="streaming_manager"),
    ]
    app.state.streaming_writer = ohlcv_writer
    app.state.streaming_manager = streaming_manager

    # ----- scheduler + jobs ----------------------------------------------
    scheduler = get_scheduler()
    register_jobs(
        scheduler,
        settings=settings,
        session_factory=SessionLocal,
        http=http,
        cache_factory=lambda: cache,
        redis_factory=lambda: redis,
        telegram_notifier=notifier,
    )
    start_scheduler()

    # ----- Telegram inbound listener -------------------------------------
    listener_task = None
    if settings.telegram_bot_token:
        def _approval_factory(session):
            from app.api.dependencies import build_execution_service_for_session

            execution = build_execution_service_for_session(
                session=session,
                http=http,
                cache=cache,
                redis=redis,
                settings=settings,
                notifier=notifier,
            )
            return ApprovalService(session=session, execution_service=execution)

        listener = TelegramBotListener(
            bot_token=settings.telegram_bot_token,
            http=http,
            session_factory=SessionLocal,
            notifier=notifier,
            approval_service_factory=_approval_factory,
        )
        listener_task = asyncio.create_task(listener.run())
        app.state.telegram_listener = listener
        app.state.telegram_listener_task = listener_task

    yield

    if listener_task is not None:
        listener = app.state.telegram_listener
        await listener.stop()
        listener_task.cancel()

    # Streaming bus shutdown
    await ohlcv_writer.stop()
    await streaming_manager.stop()
    for task in streaming_tasks:
        task.cancel()
    await asyncio.gather(*streaming_tasks, return_exceptions=True)

    stop_scheduler()
    await close_http_client()
    await close_redis()
    await engine.dispose()
    logger.info("dhruva.shutdown")


async def _ensure_http_singleton():
    async for client in get_http_client():
        return client
    raise RuntimeError("http_client_unavailable")


async def _ensure_redis_singleton():
    async for client in get_redis():
        return client
    raise RuntimeError("redis_unavailable")


def create_app() -> FastAPI:
    settings = get_settings()

    configure_logging(level=settings.log_level, env=settings.env)
    if settings.enable_tracing:
        configure_tracing(
            service_name=settings.service_name,
            service_version=settings.service_version,
            otlp_endpoint=settings.otlp_endpoint,
        )

    app = FastAPI(
        title="DHRUVA API",
        description="Ultra-fast algo trading & portfolio management for Indian markets.",
        version=settings.service_version,
        lifespan=lifespan,
        docs_url="/docs" if settings.env != "production" else None,
        redoc_url="/redoc" if settings.env != "production" else None,
    )

    app.add_middleware(ErrorHandlerMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(AuthContextMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready", tags=["health"])
    async def ready(session: AsyncSession = Depends(get_session)) -> Response | dict[str, object]:
        redis = None
        async for client in get_redis():
            redis = client
            break
        db_ok, db_msg = await check_db(session)
        redis_ok, redis_msg = await check_redis(redis) if redis else (False, "redis_unavailable")
        checks = {
            "db": "ok" if db_ok else db_msg,
            "redis": "ok" if redis_ok else redis_msg,
        }
        if db_ok and redis_ok:
            return {"status": "ready", "checks": checks}
        return Response(content=str({"status": "not_ready", "checks": checks}), status_code=503)

    @app.get("/metrics", tags=["observability"])
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(orders.router, prefix="/api/v1", tags=["orders"])
    app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
    app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
    app.include_router(instruments.router, prefix="/api/v1", tags=["instruments"])
    app.include_router(options.router, prefix="/api/v1", tags=["options"])
    app.include_router(advisor.router, prefix="/api/v1/advisor", tags=["advisor"])
    app.include_router(scanners.router, prefix="/api/v1/scanners", tags=["scanners"])
    app.include_router(scan_results.router, prefix="/api/v1/scan-results", tags=["scanners"])
    app.include_router(fundamentals.router, prefix="/api/v1/fundamentals", tags=["fundamentals"])
    app.include_router(market_cycle.router, prefix="/api/v1/market-cycle", tags=["market-cycle"])
    app.include_router(goals.router, prefix="/api/v1/goals", tags=["goals"])
    app.include_router(watchlists.router, prefix="/api/v1/watchlists", tags=["watchlists"])
    app.include_router(webhooks.router_chartink, prefix="/api/v1/webhooks/chartink", tags=["webhooks"])
    app.include_router(webhooks.router_tradingview, prefix="/api/v1/webhooks/tradingview", tags=["webhooks"])
    app.include_router(webhooks_extra.router_amibroker, prefix="/api/v1/webhooks/amibroker", tags=["webhooks"])
    app.include_router(webhooks_extra.router_metatrader, prefix="/api/v1/webhooks/metatrader", tags=["webhooks"])
    app.include_router(webhooks_extra.router_gocharting, prefix="/api/v1/webhooks/gocharting", tags=["webhooks"])
    app.include_router(webhooks_extra.router_n8n, prefix="/api/v1/webhooks/n8n", tags=["webhooks"])
    app.include_router(webhooks.router_sources, prefix="/api/v1/webhook-sources", tags=["webhooks"])
    app.include_router(webhooks.router_notifications, prefix="/api/v1/notifications", tags=["notifications"])

    # Outbound market-data WebSocket. The stream_hub is created in the lifespan,
    # so the handler resolves it from app.state at connection time rather than
    # binding at module import.
    from fastapi import WebSocket

    from app.api.websocket.streaming import _pump, _safe_parse

    @app.websocket("/ws/market")
    async def market_ws(ws: WebSocket) -> None:
        await ws.accept()
        hub = app.state.stream_hub
        tasks: dict[str, asyncio.Task] = {}
        try:
            while True:
                raw = await ws.receive_text()
                msg = _safe_parse(raw)
                if not msg:
                    continue
                action = msg.get("action")
                channel = msg.get("channel")
                if not isinstance(channel, str):
                    continue
                if action == "subscribe" and channel not in tasks:
                    tasks[channel] = asyncio.create_task(_pump(ws, hub, channel))
                elif action == "unsubscribe" and channel in tasks:
                    tasks[channel].cancel()
                    del tasks[channel]
        except Exception:  # noqa: BLE001
            pass
        finally:
            for t in tasks.values():
                t.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    RedisInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()

    return app


app = create_app()
