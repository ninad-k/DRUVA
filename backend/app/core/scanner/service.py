"""CRUD service for ScannerConfig + ScanResult."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models.scanner import (
    ScannerCadence,
    ScannerConfig,
    ScanResult,
    ScanResultStatus,
)


@dataclass
class ScannerService:
    session: AsyncSession

    # ---------------------------------------------------------- ScannerConfig
    async def create(
        self,
        *,
        account_id: UUID,
        name: str,
        scanner_class: str,
        parameters: dict[str, Any] | None = None,
        cadence: ScannerCadence | str = ScannerCadence.DAILY,
    ) -> ScannerConfig:
        if isinstance(cadence, str):
            cadence = ScannerCadence(cadence)
        row = ScannerConfig(
            account_id=account_id,
            name=name,
            scanner_class=scanner_class,
            parameters=parameters or {},
            cadence=cadence,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row

    async def list(self, account_id: UUID) -> list[ScannerConfig]:
        return (
            await self.session.execute(
                select(ScannerConfig).where(
                    ScannerConfig.account_id == account_id,
                    ScannerConfig.is_deleted.is_(False),
                )
            )
        ).scalars().all()

    async def get(self, scanner_id: UUID) -> ScannerConfig:
        row = await self.session.get(ScannerConfig, scanner_id)
        if row is None or row.is_deleted:
            raise NotFoundError("scanner_not_found")
        return row

    async def update(self, scanner_id: UUID, parameters: dict[str, Any]) -> ScannerConfig:
        row = await self.get(scanner_id)
        row.parameters = parameters
        await self.session.commit()
        return row

    async def enable(self, scanner_id: UUID) -> ScannerConfig:
        row = await self.get(scanner_id)
        row.is_enabled = True
        await self.session.commit()
        return row

    async def disable(self, scanner_id: UUID) -> ScannerConfig:
        row = await self.get(scanner_id)
        row.is_enabled = False
        await self.session.commit()
        return row

    async def delete(self, scanner_id: UUID) -> ScannerConfig:
        row = await self.get(scanner_id)
        row.is_deleted = True
        row.is_enabled = False
        await self.session.commit()
        return row

    # ---------------------------------------------------------- ScanResult
    async def list_results(
        self,
        *,
        scanner_id: UUID | None = None,
        account_id: UUID | None = None,
        status: ScanResultStatus | str | None = None,
        limit: int = 200,
    ) -> list[ScanResult]:
        stmt = select(ScanResult).order_by(
            ScanResult.run_ts.desc(), ScanResult.score.desc(),
        ).limit(limit)
        if scanner_id:
            stmt = stmt.where(ScanResult.scanner_id == scanner_id)
        if account_id:
            stmt = stmt.where(
                ScanResult.scanner_id.in_(
                    select(ScannerConfig.id).where(ScannerConfig.account_id == account_id)
                )
            )
        if status:
            if isinstance(status, str):
                status = ScanResultStatus(status)
            stmt = stmt.where(ScanResult.status == status)
        return (await self.session.execute(stmt)).scalars().all()

    async def get_result(self, result_id: UUID) -> ScanResult:
        row = await self.session.get(ScanResult, result_id)
        if row is None:
            raise NotFoundError("scan_result_not_found")
        return row

    async def set_result_status(
        self, result_id: UUID, status: ScanResultStatus,
    ) -> ScanResult:
        row = await self.get_result(result_id)
        row.status = status
        await self.session.commit()
        return row
