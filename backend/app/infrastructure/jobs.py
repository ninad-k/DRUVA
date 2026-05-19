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

import asyncio
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
    email_notifier=None,  # app.core.notifications.email.EmailNotifier | None
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

    # 6. Regime executor — runs 30 min after NSE close (10:30 UTC = 16:00 IST).
    #    Fetches latest NIFTY 50 daily bar, applies HMM → VIX → circuit breaker → execution.
    if getattr(settings, "regime_trader_enabled", False):
        from app.core.execution.regime_executor import RegimeExecutor
        from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy

        async def regime_bar_job() -> None:
            import yfinance as yf
            import pandas as pd
            from datetime import datetime, timedelta

            try:
                end = datetime.utcnow()
                start = end - timedelta(days=365)
                raw = yf.download("^NSEI", start=start.strftime("%Y-%m-%d"),
                                  end=end.strftime("%Y-%m-%d"), interval="1d",
                                  auto_adjust=True, progress=False)
                if raw is None or len(raw) == 0:
                    logger.warning("regime_bar_job.no_data")
                    return
                if hasattr(raw.columns, "get_level_values"):
                    raw.columns = raw.columns.get_level_values(0)
                ohlcv = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
                ohlcv["volume"] = ohlcv["volume"].replace(0, 1).fillna(1)
                ohlcv.index = pd.to_datetime(ohlcv.index).tz_localize(None)

                async with session_factory() as session:
                    from app.api.dependencies import build_execution_service_for_session
                    cache = cache_factory()
                    exec_svc = build_execution_service_for_session(
                        session=session, http=http, cache=cache,
                        redis=redis_factory(), settings=settings, notifier=telegram_notifier,
                    )
                    strategy = RegimeTraderStrategy(id="regime_trader_main", account_id="system")
                    executor = RegimeExecutor(
                        execution_service=exec_svc,
                        strategy=strategy,
                        telegram_notifier=telegram_notifier,
                        email_notifier=email_notifier,
                        account_id="system",
                        telegram_chat_id=getattr(settings, "regime_alert_chat_id", ""),
                        alert_emails=getattr(settings, "regime_alert_emails", []),
                    )
                    result = await executor.run_daily_bar(ohlcv)
                    logger.info("scheduler.regime_bar_ok", **{k: v for k, v in result.items()
                                                              if k != "exec_summary"})
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler.regime_bar_failed", error=str(exc))

        scheduler.add_job(
            regime_bar_job,
            CronTrigger(day_of_week="mon-fri", hour=10, minute=30),
            id="regime_daily_bar",
            replace_existing=True,
        )

    # 7. Rebalance drift check — 15 min after NSE close (10:15 UTC = 15:45 IST).
    if getattr(settings, "rebalance_enabled", False):
        from app.core.portfolio.rebalance_scheduler import RebalanceScheduler

        async def rebalance_drift_job() -> None:
            try:
                async with session_factory() as session:
                    from app.api.dependencies import build_execution_service_for_session
                    cache = cache_factory()
                    exec_svc = build_execution_service_for_session(
                        session=session, http=http, cache=cache,
                        redis=redis_factory(), settings=settings, notifier=telegram_notifier,
                    )
                    target_weights = getattr(settings, "rebalance_target_weights", {})
                    rs = RebalanceScheduler(
                        execution_service=exec_svc,
                        target_weights=target_weights,
                        email_notifier=email_notifier,
                    )
                    await rs.trigger_if_needed(session=session)
            except Exception as exc:  # noqa: BLE001
                logger.warning("scheduler.rebalance_drift_failed", error=str(exc))

        scheduler.add_job(
            rebalance_drift_job,
            CronTrigger(day_of_week="mon-fri", hour=10, minute=15),
            id="rebalance_drift_check",
            replace_existing=True,
        )

    # 8. Auto square-off — 3:15 PM IST = 09:45 UTC.
    async def square_off_job() -> None:
        try:
            from app.core.intraday.square_off import AutoSquareOff
            async with session_factory() as session:
                from app.api.dependencies import build_execution_service_for_session
                cache = cache_factory()
                exec_svc = build_execution_service_for_session(
                    session=session, http=http, cache=cache,
                    redis=redis_factory(), settings=settings, notifier=telegram_notifier,
                )
                auto_sq = AutoSquareOff(execution_service=exec_svc)
                await auto_sq.square_off_intraday()
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.square_off_failed", error=str(exc))

    scheduler.add_job(
        square_off_job,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=45),
        id="auto_square_off",
        replace_existing=True,
    )

    # 9. SIP due runner — daily at market open (03:45 UTC = 09:15 IST).
    async def sip_due_job() -> None:
        try:
            from app.core.portfolio.sip_engine import SIPEngine
            async with session_factory() as session:
                from app.api.dependencies import build_execution_service_for_session
                cache = cache_factory()
                exec_svc = build_execution_service_for_session(
                    session=session, http=http, cache=cache,
                    redis=redis_factory(), settings=settings, notifier=telegram_notifier,
                )
                engine = SIPEngine(execution_service=exec_svc)
                await engine.run_due(session=session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.sip_due_failed", error=str(exc))

    scheduler.add_job(
        sip_due_job,
        CronTrigger(day_of_week="mon-fri", hour=3, minute=45),
        id="sip_due_runner",
        replace_existing=True,
    )

    # 10. HMM weekly retrain — every Sunday at 01:00 UTC.
    async def regime_weekly_retrain_job() -> None:
        try:
            from app.strategies.ml.regime_trader.retrain import retrain_regime_hmm
            result = await asyncio.to_thread(retrain_regime_hmm)
            logger.info("scheduler.regime_retrain_ok", **result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scheduler.regime_retrain_failed", error=str(exc))

    scheduler.add_job(
        regime_weekly_retrain_job,
        CronTrigger(day_of_week="sun", hour=1, minute=0),
        id="regime_weekly_retrain",
        replace_existing=True,
    )

    # 11. Daily Telegram summary — weekday 11:00 UTC = 16:30 IST.
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
