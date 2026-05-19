from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.strategy.backtest import BacktestEngine
from app.core.strategy.service import StrategyService
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.logging import get_logger
from app.strategies.registry import all_strategies

logger = get_logger(__name__)

router = APIRouter()


class StrategyCreatePayload(BaseModel):
    account_id: UUID
    name: str
    strategy_class: str
    parameters: dict[str, Any] = {}
    mode: str = "paper"
    requires_approval: bool = False
    is_ml: bool = False
    model_version: str | None = None


class StrategyUpdatePayload(BaseModel):
    parameters: dict[str, Any]


class BacktestPayload(BaseModel):
    symbols: list[str]
    timeframe: str
    start: datetime
    end: datetime


@router.post("", status_code=201)
async def create_strategy(
    payload: StrategyCreatePayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    strategy = await service.create(**payload.model_dump())
    return _strategy_to_dict(strategy)


@router.get("")
async def list_strategies(
    account_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    return [_strategy_to_dict(s) for s in await service.list(account_id)]


@router.get("/registry")
async def registry() -> list[str]:
    return sorted(all_strategies().keys())


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    strategy = await service.get(strategy_id)
    return _strategy_to_dict(strategy)


@router.patch("/{strategy_id}")
async def update_strategy(
    strategy_id: UUID,
    payload: StrategyUpdatePayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    strategy = await service.update(strategy_id, payload.parameters)
    return _strategy_to_dict(strategy)


@router.post("/{strategy_id}/enable")
async def enable_strategy(
    strategy_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    return _strategy_to_dict(await service.enable(strategy_id))


@router.post("/{strategy_id}/disable")
async def disable_strategy(
    strategy_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    return _strategy_to_dict(await service.disable(strategy_id))


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    return _strategy_to_dict(await service.delete(strategy_id))


@router.post("/{strategy_id}/backtest")
async def backtest(
    strategy_id: UUID,
    payload: BacktestPayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    service = StrategyService(session=session, audit_service=None)  # type: ignore[arg-type]
    strategy = await service.get(strategy_id)
    engine = BacktestEngine(session=session)
    result = await engine.run(
        strategy_class=strategy.strategy_class,
        parameters=strategy.parameters,
        symbols=payload.symbols,
        timeframe=payload.timeframe,
        start=payload.start,
        end=payload.end,
    )
    return {
        "metrics": {
            "total_return": str(result.metrics.total_return),
            "sharpe": str(result.metrics.sharpe),
            "sortino": str(result.metrics.sortino),
            "calmar": str(result.metrics.calmar),
            "max_drawdown": str(result.metrics.max_drawdown),
            "win_rate": str(result.metrics.win_rate),
            "trades": result.metrics.trades,
        },
        "equity_curve": result.equity_curve,
        "trades": [trade.__dict__ for trade in result.trades],
    }


@router.post("/regime-trader/retrain")
async def retrain_regime_trader(
    background_tasks: BackgroundTasks,
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Trigger an on-demand HMM retrain. Returns immediately; retrain runs in background."""
    from app.strategies.ml.regime_trader.retrain import retrain_regime_hmm

    job_id = str(uuid.uuid4())

    async def _run() -> None:
        logger.info("retrain.endpoint_triggered", job_id=job_id)
        try:
            result = await asyncio.to_thread(retrain_regime_hmm)
            logger.info("retrain.endpoint_ok", job_id=job_id, **result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrain.endpoint_failed", job_id=job_id, error=str(exc))

    background_tasks.add_task(_run)
    return {"status": "retrain_started", "job_id": job_id}


def _strategy_to_dict(strategy) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "id": str(strategy.id),
        "account_id": str(strategy.account_id),
        "name": strategy.name,
        "strategy_class": strategy.strategy_class,
        "is_enabled": strategy.is_enabled,
        "requires_approval": strategy.requires_approval,
        "mode": str(strategy.mode),
        "is_ml": strategy.is_ml,
        "model_version": strategy.model_version,
        "parameters": strategy.parameters,
    }
