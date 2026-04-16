from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_approval_service
from app.core.auth.dependencies import get_current_user
from app.core.execution.approval_service import ApprovalService
from app.db.models.approval import ApprovalRequest
from app.db.models.user import User

router = APIRouter()


@router.get("", response_model=list[dict[str, object]])
async def list_approvals(
    account_id: UUID,
    status: str = Query("pending"),
    _user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> list[dict[str, object]]:
    approvals = await service.list(account_id, status)
    return [_to_dict(item) for item in approvals]


@router.post("/{approval_id}/approve")
async def approve(
    approval_id: UUID,
    user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> dict[str, object]:
    order = await service.approve(str(user.id), approval_id)
    return {"order_id": str(order.id), "status": order.status}


@router.post("/{approval_id}/reject")
async def reject(
    approval_id: UUID,
    user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
) -> dict[str, object]:
    approval = await service.reject(str(user.id), approval_id)
    return _to_dict(approval)


def _to_dict(item: ApprovalRequest) -> dict[str, object]:
    return {
        "id": str(item.id),
        "account_id": str(item.account_id),
        "strategy_id": str(item.strategy_id) if item.strategy_id else None,
        "status": item.status,
        "requested_at": item.requested_at.isoformat(),
        "signal": item.signal_jsonb,
    }
