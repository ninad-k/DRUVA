from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.event_store import AuditService
from app.core.errors import NotFoundError
from app.db.models.strategy import Strategy


@dataclass
class StrategyService:
    session: AsyncSession
    audit_service: AuditService | None

    async def create(
        self,
        account_id: UUID,
        name: str,
        strategy_class: str,
        parameters: dict[str, Any],
        mode: str,
        requires_approval: bool,
        is_ml: bool,
        model_version: str | None,
    ) -> Strategy:
        strategy = Strategy(
            account_id=account_id,
            name=name,
            strategy_class=strategy_class,
            parameters=parameters,
            mode=mode,
            requires_approval=requires_approval,
            is_ml=is_ml,
            model_version=model_version,
        )
        self.session.add(strategy)
        await self.session.commit()
        await self.session.refresh(strategy)
        return strategy

    async def list(self, account_id: UUID) -> list[Strategy]:
        return (
            await self.session.execute(
                select(Strategy).where(Strategy.account_id == account_id, Strategy.is_deleted.is_(False))
            )
        ).scalars().all()

    async def get(self, strategy_id: UUID) -> Strategy:
        strategy = await self.session.get(Strategy, strategy_id)
        if strategy is None or strategy.is_deleted:
            raise NotFoundError("strategy_not_found")
        return strategy

    async def enable(self, strategy_id: UUID) -> Strategy:
        strategy = await self.get(strategy_id)
        strategy.is_enabled = True
        await self.session.commit()
        return strategy

    async def disable(self, strategy_id: UUID) -> Strategy:
        strategy = await self.get(strategy_id)
        strategy.is_enabled = False
        await self.session.commit()
        return strategy

    async def update(self, strategy_id: UUID, parameters: dict[str, Any]) -> Strategy:
        strategy = await self.get(strategy_id)
        strategy.parameters = parameters
        await self.session.commit()
        return strategy

    async def delete(self, strategy_id: UUID) -> Strategy:
        strategy = await self.get(strategy_id)
        strategy.is_deleted = True
        strategy.is_enabled = False
        await self.session.commit()
        return strategy
