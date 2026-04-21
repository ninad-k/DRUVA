"""APScheduler job registration.

Called from the FastAPI lifespan AFTER the scheduler has started. Each job is
short, idempotent, and creates its own AsyncSession so it doesn't share state
with HTTP requests.

Scheduled jobs:
- ``broker_health_monitor`` — every 60 s.
- ``master_contract_sync`` — every weekday at 02:30 UTC (08:00 IST).
- ``strategy_run_loop`` — every minute.
- ``daily_telegram_summary`` — every weekday at 11:00 UTC (16:30 IST).

If a job dependency is unconfigured (e.g. no Telegram bot token) the job is
skipped at registration time and we log why.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.factory import BrokerFactory
from app.brokers.health_monitor import BrokerHealthMonitor
from app.cache.client import CacheClient
from app.config import Settings
from app.core.audit.event_store import AuditService
from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.execution.position_tracker import PositionTracker
from app.core.execution.risk_engine import RiskEngine
from app.core.notifications.telegram import DailySummary, TelegramNotifier
from app.core.strategy.run_loop import StrategyRunLoop
from app.data.instruments.sync_service import InstrumentSyncService
from app.db.models.account import Account
from app.db.models.notification import NotificationConfig
from app.db.models.order import Order
from app.db.models.position import Position
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


def register_jobs(
    scheduler: AsyncIOScheduler,
    *,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    cache_factory: Callable[[], CacheClient],
    redis_factory: Callable[[], Redis],
    telegram_notifier: TelegramNotifier,
) -> None:
    # 1. Broker health monitor — every 60 s.
    async def health_job() -> None:
        async with session_factory() as session:
            cache = cache_factory()
            broker_factory = BrokerFactory(http=http, settings=settings, cache=cache)
            monitor = BrokerHealthMonitor(session=session, factory=broker_factory)
            try:
                await monitor.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler.health_job_failed", error=str(exc))

    scheduler.add_job(
        health_job,
        IntervalTrigger(seconds=60),
        id="broker_health_monitor",
        replace_existing=True,
    )

    # 2. Master-contract sync — every weekday 02:30 UTC = 08:00 IST.
    async def sync_job() -> None:
        async with session_factory() as session:
            cache = cache_factory()
            broker_factory = BrokerFactory(http=http, settings=settings, cache=cache)
            audit = AuditService()
            sync = InstrumentSyncService(
                session=session, factory=broker_factory, audit_service=audit
            )
            broker_ids = (
                await session.execute(
                    select(Account.broker_id)
                    .where(Account.is_active.is_(True))
                    .distinct()
                )
            ).scalars().all()
            for broker_id in broker_ids:
                try:
                    await sync.sync_broker(broker_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "scheduler.sync_failed", broker=broker_id, error=str(exc)
                    )

    scheduler.add_job(
        sync_job,
        CronTrigger(day_of_week="mon-fri", hour=2, minute=30),
        id="master_contract_sync",
        replace_existing=True,
    )

    # 3. Strategy run loop — every minute.
    run_loop = StrategyRunLoop(
        session_factory=session_factory,
        http=http,
        cache_factory=cache_factory,
        redis_factory=redis_factory,
        settings=settings,
    )

    async def strategy_job() -> None:
        try:
            dispatched = await run_loop.run_once()
            if dispatched:
                logger.info("scheduler.strategy_dispatched", count=dispatched)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.strategy_loop_failed", error=str(exc))

    scheduler.add_job(
        strategy_job,
        IntervalTrigger(minutes=1),
        id="strategy_run_loop",
        replace_existing=True,
    )

    # 4. AI Advisor daily refresh — after NSE close (13:00 UTC = 18:30 IST by default).
    if settings.advisor_enabled:
        from app.core.advisor.service import AdvisorService, fallback_llm_from_settings
        from app.db.models.advisor import AdvisorWatchlist

        async def advisor_job() -> None:
            async with session_factory() as session:
                # Run for every user that has an active watchlist entry.
                user_ids = (
                    await session.execute(
                        select(AdvisorWatchlist.user_id)
                        .where(AdvisorWatchlist.is_active.is_(True))
                        .distinct()
                    )
                ).scalars().all()
                fallback = fallback_llm_from_settings(settings)
                for uid in user_ids:
                    try:
                        svc = AdvisorService(
                            session=session, http=http, fallback_llm=fallback,
                        )
                        result = await svc.run(user_id=uid)
                        logger.info(
                            "scheduler.advisor_run_ok",
                            user_id=str(uid),
                            scored=result.scored,
                            regime=result.regime.value,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "scheduler.advisor_run_failed",
                            user_id=str(uid),
                            error=str(exc),
                        )

        scheduler.add_job(
            advisor_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=settings.advisor_refresh_cron_utc_hour,
                minute=settings.advisor_refresh_cron_utc_minute,
            ),
            id="advisor_daily_refresh",
            replace_existing=True,
        )

    # 5a. Scanner run-all — post-close daily.
    if settings.scanner_enabled:
        from app.core.scanner.runner import ScannerRunner

        async def scanner_job() -> None:
            async with session_factory() as session:
                try:
                    runner = ScannerRunner(session=session)
                    total = await runner.run_all_enabled()
                    if total:
                        logger.info("scheduler.scanner_run_ok", emitted=total)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("scheduler.scanner_run_failed", error=str(exc))

        scheduler.add_job(
            scanner_job,
            CronTrigger(
                day_of_week="mon-fri",
                hour=settings.scanner_run_cron_utc_hour,
                minute=settings.scanner_run_cron_utc_minute,
            ),
            id="scanner_daily_run",
            replace_existing=True,
        )

        # 5b. Fundamentals weekly refresh (Saturday by default).
        from app.data.fundamentals.refresh_job import FundamentalsRefreshJob

        async def fundamentals_job() -> None:
            async with session_factory() as session:
                try:
                    job = FundamentalsRefreshJob(
                        session=session, http=http, settings=settings,
                    )
                    result = await job.run(limit=500)
                    logger.info("scheduler.fundamentals_refresh_ok", **result)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "scheduler.fundamentals_refresh_failed", error=str(exc),
                    )

        scheduler.add_job(
            fundamentals_job,
            CronTrigger(
                day_of_week=settings.fundamentals_refresh_day_of_week,
                hour=settings.fundamentals_refresh_cron_utc_hour,
                minute=settings.fundamentals_refresh_cron_utc_minute,
            ),
            id="fundamentals_weekly_refresh",
            replace_existing=True,
        )

    # 6. Daily Telegram summary — weekday 11:00 UTC = 16:30 IST.
    if not settings.telegram_bot_token:
        logger.info("scheduler.daily_summary_skipped", reason="no_telegram_token")
        return

    async def daily_summary_job() -> None:
        async with session_factory() as session:
            configs = (
                await session.execute(
                    select(NotificationConfig).where(
                        NotificationConfig.channel == "telegram",
                        NotificationConfig.is_active.is_(True),
                    )
                )
            ).scalars().all()
            for cfg in configs:
                accounts = (
                    await session.execute(
                        select(Account).where(Account.user_id == cfg.user_id)
                    )
                ).scalars().all()
                account_ids = [a.id for a in accounts]
                if not account_ids:
                    continue
                positions = (
                    await session.execute(
                        select(Position).where(Position.account_id.in_(account_ids))
                    )
                ).scalars().all()
                orders = (
                    await session.execute(
                        select(Order).where(Order.account_id.in_(account_ids))
                    )
                ).scalars().all()
                summary = DailySummary(
                    pnl=str(sum((p.realized_pnl for p in positions), start=0)),
                    orders=len(orders),
                    positions=len(positions),
                )
                await telegram_notifier.send_daily_summary(cfg.destination, summary)

    scheduler.add_job(
        daily_summary_job,
        CronTrigger(day_of_week="mon-fri", hour=11, minute=0),
        id="daily_telegram_summary",
        replace_existing=True,
    )
