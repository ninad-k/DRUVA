"""Periodic strategy dispatch.

Called from the APScheduler in ``app.main`` once per minute. For every enabled
strategy, fetches the most recent OHLCV candle and dispatches it via
StrategyExecutor.

If no candle is available yet (e.g. first run, no data fed), the strategy is
skipped — strategies must not see ``None`` from the dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.factory import BrokerFactory
from app.cache.client import CacheClient
from app.config import Settings
from app.core.audit.event_store import AuditService
from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.execution.position_tracker import PositionTracker
from app.core.execution.risk_engine import RiskEngine
from app.core.strategy.executor import StrategyExecutor
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.strategy import Strategy
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StrategyRunLoop:
    """Owns its dependencies so APScheduler can call it without going through
    FastAPI's per-request DI container."""

    session_factory: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    cache_factory: Callable[[], CacheClient]
    redis_factory: Callable[[], Redis]
    settings: Settings

    async def run_once(self) -> int:
        """Process every enabled strategy once. Returns number dispatched."""
        dispatched = 0
        async with self.session_factory() as session:
            strategies = (
                await session.execute(
                    select(Strategy).where(
                        Strategy.is_enabled.is_(True),
                        Strategy.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            if not strategies:
                return 0

            executor = self._build_executor(session)
            ohlcv = OhlcvRepository(session)

            for strategy in strategies:
                params: dict[str, Any] = strategy.parameters or {}
                symbols = params.get("symbols") or []
                timeframe = params.get("timeframe", "1m")
                exchange = params.get("exchange", "NSE")
                for symbol in symbols:
                    candles = await ohlcv.latest(
                        symbol=str(symbol),
                        exchange=exchange,
                        timeframe=timeframe,
                        limit=1,
                    )
                    if not candles:
                        logger.debug(
                            "strategy.no_candle",
                            strategy_id=str(strategy.id),
                            symbol=symbol,
                        )
                        continue
                    try:
                        await executor.execute_one(strategy.id, candles[-1])
                        dispatched += 1
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            "strategy.execute_failed",
                            strategy_id=str(strategy.id),
                            symbol=symbol,
                            error=str(exc),
                        )
        return dispatched

    def _build_executor(self, session: AsyncSession) -> StrategyExecutor:
        cache = self.cache_factory()
        redis = self.redis_factory()
        broker_factory = BrokerFactory(http=self.http, settings=self.settings, cache=cache)
        execution = ExecutionService(
            session=session,
            broker_factory=broker_factory,
            audit_service=AuditService(),
            risk_engine=RiskEngine(
                session=session, redis=redis, broker_factory=broker_factory
            ),
            position_tracker=PositionTracker(session=session, cache=cache),
        )
        approval = ApprovalService(session=session, execution_service=execution)
        return StrategyExecutor(
            session=session,
            execution_service=execution,
            approval_service=approval,
        )
