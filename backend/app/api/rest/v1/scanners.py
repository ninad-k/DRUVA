"""Scanner configuration + run endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.scanner.backtest import ScannerBacktestEngine
from app.core.scanner.registry import all_scanners
from app.core.scanner.runner import ScannerRunner
from app.core.scanner.service import ScannerService
from app.db.models.scanner import ScannerCadence
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter()


class ScannerCreatePayload(BaseModel):
    account_id: UUID
    name: str
    scanner_class: str
    parameters: dict[str, Any] = {}
    cadence: str = "daily"


class ScannerUpdatePayload(BaseModel):
    parameters: dict[str, Any]


class BacktestPayload(BaseModel):
    start: date
    end: date
    initial_equity: float = 1_000_000.0
    step_days: int = 7


@router.get("/registry")
async def registry() -> list[str]:
    return sorted(all_scanners().keys())


@router.post("", status_code=201)
async def create_scanner(
    payload: ScannerCreatePayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    row = await svc.create(
        account_id=payload.account_id,
        name=payload.name,
        scanner_class=payload.scanner_class,
        parameters=payload.parameters,
        cadence=ScannerCadence(payload.cadence),
    )
    return _to_dict(row)


@router.get("")
async def list_scanners(
    account_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    svc = ScannerService(session=session)
    return [_to_dict(s) for s in await svc.list(account_id)]


@router.get("/{scanner_id}")
async def get_scanner(
    scanner_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    return _to_dict(await svc.get(scanner_id))


@router.patch("/{scanner_id}")
async def update_scanner(
    scanner_id: UUID,
    payload: ScannerUpdatePayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    return _to_dict(await svc.update(scanner_id, payload.parameters))


@router.post("/{scanner_id}/enable")
async def enable_scanner(
    scanner_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    return _to_dict(await svc.enable(scanner_id))


@router.post("/{scanner_id}/disable")
async def disable_scanner(
    scanner_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    return _to_dict(await svc.disable(scanner_id))


@router.delete("/{scanner_id}")
async def delete_scanner(
    scanner_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    return _to_dict(await svc.delete(scanner_id))


@router.post("/{scanner_id}/run-now")
async def run_now(
    scanner_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    cfg = await svc.get(scanner_id)
    runner = ScannerRunner(session=session)
    count = await runner.run_one(cfg)
    return {"scanner_id": str(scanner_id), "emitted": count}


@router.post("/{scanner_id}/backtest")
async def backtest(
    scanner_id: UUID,
    payload: BacktestPayload,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    from decimal import Decimal

    svc = ScannerService(session=session)
    cfg = await svc.get(scanner_id)
    engine = ScannerBacktestEngine(session=session)
    result = await engine.run(
        scanner_class=cfg.scanner_class,
        parameters=cfg.parameters or {},
        start=payload.start,
        end=payload.end,
        initial_equity=Decimal(str(payload.initial_equity)),
        step_days=payload.step_days,
    )
    return {
        "metrics": {
            "total_return_pct": str(result.metrics.total_return_pct),
            "cagr_pct": str(result.metrics.cagr_pct),
            "sharpe": str(result.metrics.sharpe),
            "max_drawdown_pct": str(result.metrics.max_drawdown_pct),
            "win_rate_pct": str(result.metrics.win_rate_pct),
            "avg_hold_days": str(result.metrics.avg_hold_days),
            "trades": result.metrics.trades,
            "multibagger_2x": result.metrics.multibagger_2x,
            "multibagger_5x": result.metrics.multibagger_5x,
            "multibagger_10x": result.metrics.multibagger_10x,
        },
        "equity_curve": [
            {"ts": ts.isoformat(), "equity": str(eq)} for ts, eq in result.equity_curve
        ],
        "trades": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date.isoformat(),
                "exit_date": t.exit_date.isoformat(),
                "entry_price": str(t.entry_price),
                "exit_price": str(t.exit_price),
                "pnl": str(t.pnl),
                "return_pct": str(t.return_pct),
                "hold_days": t.hold_days,
            }
            for t in result.trades
        ],
    }


def _to_dict(row) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "id": str(row.id),
        "account_id": str(row.account_id),
        "name": row.name,
        "scanner_class": row.scanner_class,
        "parameters": row.parameters,
        "cadence": str(row.cadence),
        "is_enabled": row.is_enabled,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
    }
