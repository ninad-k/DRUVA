"""ScanResult read + promote endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_approval_service
from app.core.auth.dependencies import get_current_user
from app.core.execution.approval_service import ApprovalService
from app.core.scanner.promote import ScannerPromoter
from app.core.scanner.service import ScannerService
from app.db.models.scanner import ScanResult, ScanResultStatus
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter()


class PromotePayload(BaseModel):
    capital_inr: float | None = None


@router.get("")
async def list_scan_results(
    scanner_id: UUID | None = Query(None),
    account_id: UUID | None = Query(None),
    status: str | None = Query("new"),
    limit: int = Query(200, ge=1, le=1000),
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    svc = ScannerService(session=session)
    rows = await svc.list_results(
        scanner_id=scanner_id, account_id=account_id, status=status, limit=limit,
    )
    return [_to_dict(r) for r in rows]


@router.post("/{result_id}/acknowledge")
async def acknowledge(
    result_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    row = await svc.set_result_status(result_id, ScanResultStatus.ACKNOWLEDGED)
    return _to_dict(row)


@router.post("/{result_id}/dismiss")
async def dismiss(
    result_id: UUID,
    _user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    row = await svc.set_result_status(result_id, ScanResultStatus.DISMISSED)
    return _to_dict(row)


@router.post("/{result_id}/promote")
async def promote(
    result_id: UUID,
    payload: PromotePayload | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> dict[str, object]:
    svc = ScannerService(session=session)
    row = await svc.get_result(result_id)
    promoter = ScannerPromoter(session=session, approval_service=approval_service)
    capital = Decimal(str(payload.capital_inr)) if payload and payload.capital_inr else None
    result = await promoter.promote(user_id=str(user.id), result=row, capital_inr=capital)
    return {
        "result_id": str(result_id),
        "approval_id": str(result.approval_id) if result.approval_id else None,
        "reason": result.reason,
    }


def _to_dict(row: ScanResult) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "scanner_id": str(row.scanner_id),
        "run_ts": row.run_ts.isoformat(),
        "symbol": row.symbol,
        "exchange": row.exchange,
        "score": float(row.score),
        "stage": row.stage,
        "reason": row.reason,
        "suggested_entry": float(row.suggested_entry) if row.suggested_entry is not None else None,
        "suggested_stop": float(row.suggested_stop) if row.suggested_stop is not None else None,
        "suggested_target": float(row.suggested_target) if row.suggested_target is not None else None,
        "status": str(row.status),
        "metadata": row.metadata_jsonb,
    }
