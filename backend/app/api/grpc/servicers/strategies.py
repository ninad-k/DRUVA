"""gRPC StrategyService servicer implementation."""

from __future__ import annotations

import json
from uuid import UUID

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import select

from app.api.grpc._generated.dhruva.v1 import strategies_pb2, strategies_pb2_grpc
from app.api.grpc.servicers._helpers import require_auth, ts_from_dt
from app.core.strategy.service import StrategyService
from app.db.models.common import StrategyMode
from app.db.models.strategy import Strategy
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_MODE_TO_PROTO = {
    "paper": strategies_pb2.StrategyMode.PAPER,
    "live": strategies_pb2.StrategyMode.LIVE,
}
_PROTO_TO_MODE = {v: k for k, v in _MODE_TO_PROTO.items()}


def _strategy_to_proto(s: Strategy) -> strategies_pb2.Strategy:
    mode_val = s.mode.value if hasattr(s.mode, "value") else str(s.mode)
    return strategies_pb2.Strategy(
        id=str(s.id),
        account_id=str(s.account_id),
        name=s.name,
        strategy_class=s.strategy_class,
        parameters_json=json.dumps(s.parameters) if s.parameters else "{}",
        is_enabled=s.is_enabled,
        is_ml=s.is_ml,
        model_version=s.model_version or "",
        mode=_MODE_TO_PROTO.get(mode_val.lower(), strategies_pb2.StrategyMode.PAPER),
        created_at=ts_from_dt(s.created_at),
    )


class StrategyServicer(strategies_pb2_grpc.StrategyServiceServicer):
    """Implements dhruva.v1.StrategyService over gRPC."""

    async def Create(self, request: strategies_pb2.CreateStrategyRequest, context: grpc.aio.ServicerContext) -> strategies_pb2.Strategy:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                svc = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
                mode_str = _PROTO_TO_MODE.get(request.mode, "paper")
                strategy = await svc.create(
                    account_id=UUID(request.account_id),
                    name=request.name,
                    strategy_class=request.strategy_class,
                    parameters=json.loads(request.parameters_json) if request.parameters_json else {},
                    mode=mode_str,
                    requires_approval=False,
                    is_ml=request.is_ml,
                    model_version=request.model_version or None,
                )
                return _strategy_to_proto(strategy)
            except Exception as exc:
                logger.warning("grpc.strategies.create_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def List(self, request: strategies_pb2.ListStrategiesRequest, context: grpc.aio.ServicerContext) -> strategies_pb2.ListStrategiesResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                svc = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
                strategies = await svc.list(UUID(request.account_id))
                return strategies_pb2.ListStrategiesResponse(
                    strategies=[_strategy_to_proto(s) for s in strategies]
                )
            except Exception as exc:
                logger.warning("grpc.strategies.list_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def Toggle(self, request: strategies_pb2.ToggleStrategyRequest, context: grpc.aio.ServicerContext) -> strategies_pb2.Strategy:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                svc = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
                strategy = await svc.toggle(UUID(request.strategy_id), enabled=request.enabled)
                return _strategy_to_proto(strategy)
            except Exception as exc:
                logger.warning("grpc.strategies.toggle_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def Backtest(self, request: strategies_pb2.BacktestRequest, context: grpc.aio.ServicerContext) -> strategies_pb2.BacktestResult:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                from app.core.strategy.backtest import BacktestEngine
                from datetime import datetime, timezone
                engine = BacktestEngine(session=session)
                start = request.from_ts.ToDatetime().replace(tzinfo=timezone.utc) if request.HasField("from_ts") else None
                end = request.to_ts.ToDatetime().replace(tzinfo=timezone.utc) if request.HasField("to_ts") else None
                result = await engine.run(
                    strategy_id=UUID(request.strategy_id),
                    symbols=list(request.symbols),
                    timeframe=request.timeframe or "1d",
                    start=start,
                    end=end,
                )
                return strategies_pb2.BacktestResult(
                    report_id=result.get("report_id", ""),
                    metrics_json=json.dumps(result.get("metrics", {})),
                    equity_curve_json=json.dumps(result.get("equity_curve", [])),
                    trade_list_json=json.dumps(result.get("trades", [])),
                )
            except Exception as exc:
                logger.warning("grpc.strategies.backtest_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))
