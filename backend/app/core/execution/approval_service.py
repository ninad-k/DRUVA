"""Action-Center approval workflow.

When a strategy with ``requires_approval`` produces a signal, the
ExecutionService stores both an Order (status ``pending_approval``) and an
ApprovalRequest linked to it. This service drives the approve/reject decision:

- ``approve``: marks the approval row, then submits the order to the broker
  (re-using the original signal payload). The placeholder Order is marked
  ``cancelled`` because the live order replaces it; callers see the new id.
- ``reject``: marks the approval row and the linked Order as ``cancelled``.
- Expired approvals (past ``expires_at``) cannot be approved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit.event_store import AuditService
from app.core.errors import NotFoundError, ValidationError
from app.core.execution.execution_service import ExecutionService
from app.core.execution.models import PlaceOrderRequest
from app.db.models.approval import ApprovalRequest
from app.db.models.order import Order
from app.utils.time import utcnow


@dataclass
class ApprovalService:
    session: AsyncSession
    execution_service: ExecutionService
    audit_service: AuditService = field(default_factory=AuditService)

    async def list(self, account_id: UUID, status: str = "pending") -> list[ApprovalRequest]:
        return (
            await self.session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.account_id == account_id,
                    ApprovalRequest.status == status,
                )
            )
        ).scalars().all()

    async def create(
        self,
        account_id: UUID,
        strategy_id: UUID | None,
        signal_payload: dict[str, object],
        order_id: UUID | None = None,
    ) -> ApprovalRequest:
        settings = get_settings()
        approval = ApprovalRequest(
            account_id=account_id,
            strategy_id=strategy_id,
            order_id=order_id,
            signal_jsonb=signal_payload,
            status="pending",
            requested_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=settings.approval_ttl_minutes),
        )
        self.session.add(approval)
        await self.session.commit()
        await self.session.refresh(approval)
        return approval

    async def approve(self, user_id: str, approval_id: UUID):
        approval = await self.session.get(ApprovalRequest, approval_id)
        if approval is None:
            raise NotFoundError("approval_not_found")
        if approval.status != "pending":
            raise ValidationError("approval_not_pending")
        if approval.expires_at < utcnow():
            approval.status = "expired"
            await self.session.commit()
            raise ValidationError("approval_expired")

        approval.status = "approved"
        approval.decided_at = utcnow()
        approval.decided_by_user_id = UUID(user_id)
        # Cancel the placeholder before re-placing — the new Order replaces it.
        if approval.order_id is not None:
            placeholder = await self.session.get(Order, approval.order_id)
            if placeholder is not None and placeholder.status == "pending_approval":
                placeholder.status = "cancelled"
        await self.session.commit()

        payload = PlaceOrderRequest.model_validate(approval.signal_jsonb)
        return await self.execution_service.place_order(user_id, payload)

    async def reject(self, user_id: str, approval_id: UUID) -> ApprovalRequest:
        approval = await self.session.get(ApprovalRequest, approval_id)
        if approval is None:
            raise NotFoundError("approval_not_found")
        if approval.status != "pending":
            raise ValidationError("approval_not_pending")
        approval.status = "rejected"
        approval.decided_at = utcnow()
        approval.decided_by_user_id = UUID(user_id)
        if approval.order_id is not None:
            order = await self.session.get(Order, approval.order_id)
            if order is not None and order.status == "pending_approval":
                order.status = "cancelled"
        await self.session.commit()
        return approval
