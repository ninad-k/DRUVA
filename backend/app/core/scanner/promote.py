"""ScanResult promotion — converts a candidate into an ApprovalRequest.

Sizing uses ``core.portfolio.allocator.PositionSizer`` (market-cycle aware).
The existing ``ApprovalService.create`` is reused verbatim so scanner-originated
orders flow through the same Action Center UI as any other semi-auto signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.errors import NotFoundError, ValidationError
from app.core.execution.approval_service import ApprovalService
from app.core.portfolio.allocator import PositionSizer
from app.db.models.account import Account
from app.db.models.scanner import ScanResult, ScanResultStatus
from app.db.models.scanner import ScannerConfig


@dataclass
class PromotionResult:
    approval_id: UUID | None
    reason: str | None = None


@dataclass
class ScannerPromoter:
    session: AsyncSession
    approval_service: ApprovalService
    settings: Settings = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_settings()

    async def promote(
        self,
        *,
        user_id: str,
        result: ScanResult,
        capital_inr: Decimal | None = None,
    ) -> PromotionResult:
        if result.status in (ScanResultStatus.PROMOTED, ScanResultStatus.DISMISSED):
            raise ValidationError("scan_result_terminal_state")

        cfg = await self.session.get(ScannerConfig, result.scanner_id)
        if cfg is None:
            raise NotFoundError("scanner_config_missing")
        account = await self.session.get(Account, cfg.account_id)
        if account is None:
            raise NotFoundError("account_not_found")

        sizer = PositionSizer(session=self.session, settings=self.settings)
        price = result.suggested_entry or Decimal("0")
        qty, reason = await sizer.size(
            account=account,
            symbol=result.symbol,
            exchange=result.exchange,
            score=float(result.score),
            price=price,
            capital_inr=capital_inr,
        )
        if qty <= 0:
            # Mark acknowledged so it stops showing as "new" but keeps context.
            result.status = ScanResultStatus.ACKNOWLEDGED
            await self.session.commit()
            return PromotionResult(approval_id=None, reason=reason or "zero_quantity")

        signal_payload = {
            "account_id": str(cfg.account_id),
            "symbol": result.symbol,
            "exchange": result.exchange,
            "side": "BUY",
            "quantity": str(qty),
            "order_type": "LIMIT" if price > 0 else "MARKET",
            "product": "CNC",
            "price": str(price) if price > 0 else None,
            "stop_loss": str(result.suggested_stop) if result.suggested_stop else None,
            "take_profit": str(result.suggested_target) if result.suggested_target else None,
            "strategy_id": None,
            "tag": f"scanner:{cfg.scanner_class}",
        }
        approval = await self.approval_service.create(
            account_id=cfg.account_id,
            strategy_id=None,
            signal_payload=signal_payload,
            order_id=None,
        )
        result.status = ScanResultStatus.PROMOTED
        result.promoted_approval_id = approval.id
        await self.session.commit()
        return PromotionResult(approval_id=approval.id, reason=None)
