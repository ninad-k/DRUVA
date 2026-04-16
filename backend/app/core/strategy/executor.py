"""Strategy execution glue.

Loads the registered strategy class for a stored Strategy row, builds a real
StrategyContext (PositionTracker + OhlcvRepository), invokes ``on_candle``,
then routes the resulting Signal either through ApprovalService (semi-auto)
or directly through ExecutionService (auto).

Key fixes vs. the prior version:
- Uses ``account.user_id`` as the actor; no more synthetic
  ``00000000-0000-…`` UUID polluting audit rows.
- ``StrategyExecutionContext.get_position`` returns the real signed position
  quantity from PositionTracker (was ``Decimal("0")``).
- ``StrategyExecutionContext.get_candles`` reads from OhlcvRepository (was
  always returning ``[]``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution.approval_service import ApprovalService
from app.core.execution.execution_service import ExecutionService
from app.core.execution.models import PlaceOrderRequest
from app.core.execution.position_tracker import PositionTracker
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.account import Account
from app.db.models.strategy import Strategy
from app.infrastructure.logging import get_logger
from app.infrastructure.metrics import ml_predictions_total, strategy_executions_total
from app.infrastructure.tracing import get_tracer
from app.strategies.base import Candle, Signal
from app.strategies.registry import get_strategy_class

tracer = get_tracer(__name__)
logger = get_logger(__name__)


@dataclass
class StrategyExecutionContext:
    """Runtime context handed to a Strategy on every ``on_candle`` call."""

    execution_service: ExecutionService
    position_tracker: PositionTracker
    ohlcv: OhlcvRepository
    account_id: UUID
    actor_user_id: str

    async def place_order(self, signal: Signal) -> str:
        order = await self.execution_service.place_order(
            user_id=self.actor_user_id,
            req=_signal_to_request(signal, self.account_id),
        )
        return str(order.id)

    async def get_position(self, symbol: str) -> Decimal:
        position = await self.position_tracker.get(str(self.account_id), symbol)
        return position.quantity if position is not None else Decimal("0")

    async def get_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        # Default exchange falls back to NSE; strategies can override per signal
        # via metadata if they need to look at NFO/MCX.
        return await self.ohlcv.latest(
            symbol=symbol,
            exchange="NSE",
            timeframe=timeframe,
            limit=limit,
        )


@dataclass
class StrategyExecutor:
    session: AsyncSession
    execution_service: ExecutionService
    approval_service: ApprovalService

    async def execute_one(self, strategy_id: UUID, candle: Candle) -> Signal | None:
        with tracer.start_as_current_span("strategy.execute_one") as span:
            strategy = await self.session.get(Strategy, strategy_id)
            if strategy is None or not strategy.is_enabled or strategy.is_deleted:
                return None
            account = await self.session.get(Account, strategy.account_id)
            if account is None:
                logger.warning("strategy.account_missing", strategy_id=str(strategy.id))
                return None
            span.set_attribute("strategy.id", str(strategy.id))
            span.set_attribute("strategy.class", strategy.strategy_class)

            strategy_cls = get_strategy_class(strategy.strategy_class)
            instance = strategy_cls(
                id=str(strategy.id),
                account_id=str(strategy.account_id),
                parameters=strategy.parameters,
            )
            context = StrategyExecutionContext(
                execution_service=self.execution_service,
                position_tracker=self.execution_service.position_tracker,
                ohlcv=OhlcvRepository(self.session),
                account_id=strategy.account_id,
                actor_user_id=str(account.user_id),
            )

            signal = await instance.on_candle(candle, context)
            if signal is None:
                strategy_executions_total.labels(
                    strategy=strategy.strategy_class, result="no_signal"
                ).inc()
                return None

            actor = str(account.user_id)
            if strategy.requires_approval:
                payload = _signal_to_request(signal, strategy.account_id, strategy_id=strategy.id)
                await self.approval_service.create(
                    account_id=strategy.account_id,
                    strategy_id=strategy.id,
                    signal_payload=payload.model_dump(mode="json"),
                )
                strategy_executions_total.labels(
                    strategy=strategy.strategy_class, result="approval_requested"
                ).inc()
                return signal

            await self.execution_service.place_order(
                user_id=actor,
                req=_signal_to_request(signal, strategy.account_id, strategy_id=strategy.id),
            )
            if strategy.is_ml:
                ml_predictions_total.labels(
                    model=strategy.strategy_class, signal=signal.side
                ).inc()
            strategy_executions_total.labels(
                strategy=strategy.strategy_class, result="executed"
            ).inc()
            return signal

    async def execute_signal_directly(self, strategy: Strategy, signal: Signal) -> Any:
        """Used by webhook receivers: bypass ``on_candle`` but go through the
        full execution + approval pipeline using the strategy's owner as actor.
        """
        account = await self.session.get(Account, strategy.account_id)
        if account is None:
            raise ValueError("strategy_account_missing")
        actor = str(account.user_id)

        payload = _signal_to_request(signal, strategy.account_id, strategy_id=strategy.id)
        if strategy.requires_approval:
            return await self.approval_service.create(
                account_id=strategy.account_id,
                strategy_id=strategy.id,
                signal_payload=payload.model_dump(mode="json"),
            )
        return await self.execution_service.place_order(actor, payload)


def _signal_to_request(
    signal: Signal,
    account_id: UUID,
    *,
    strategy_id: UUID | None = None,
) -> PlaceOrderRequest:
    exchange = "NSE"
    if signal.metadata and signal.metadata.get("exchange"):
        exchange = str(signal.metadata["exchange"])
    return PlaceOrderRequest(
        account_id=account_id,
        symbol=signal.symbol,
        exchange=exchange,
        side=signal.side,
        quantity=signal.quantity,
        order_type=signal.order_type,
        product="MIS",
        price=signal.limit_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        strategy_id=strategy_id,
        tag=signal.reason or None,
    )
