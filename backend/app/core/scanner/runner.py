"""ScannerRunner — executes a single ScannerConfig end-to-end.

Instantiates the registered scanner class, injects a DB-backed ScanContext,
runs ``scan()``, and bulk-persists emitted candidates as ``ScanResult`` rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scanner.base import (
    FundamentalSnapshotDTO,
    InstrumentRef,
    MarketCycleDTO,
    ScanCandidate,
    ScanContext,
    Scanner,
)
from app.core.scanner.registry import get_scanner_class
from app.core.scanner.universe import UniverseProvider
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.fundamentals import FundamentalSnapshot
from app.db.models.market_cycle import MarketCycleState
from app.db.models.scanner import ScannerConfig, ScanResult, ScanResultStatus
from app.infrastructure.logging import get_logger
from app.strategies.base import Candle
from app.utils.time import utcnow

logger = get_logger(__name__)


@dataclass
class _DbScanContext:
    """Concrete ScanContext backed by AsyncSession + repositories."""

    session: AsyncSession
    account_id: UUID
    scanner_id: UUID
    run_ts: Any
    _emitted: list[ScanCandidate]

    async def get_universe(self, filters: dict[str, Any] | None = None) -> list[InstrumentRef]:
        return await UniverseProvider(session=self.session).list(filters or {})

    async def get_candles(
        self, symbol: str, exchange: str, timeframe: str, limit: int,
    ) -> list[Candle]:
        repo = OhlcvRepository(session=self.session)
        return await repo.latest(
            symbol=symbol, exchange=exchange, timeframe=timeframe, limit=limit,
        )

    async def get_fundamentals(
        self, symbol: str, exchange: str,
    ) -> FundamentalSnapshotDTO | None:
        row = (
            await self.session.execute(
                select(FundamentalSnapshot)
                .where(
                    FundamentalSnapshot.symbol == symbol,
                    FundamentalSnapshot.exchange == exchange,
                )
                .order_by(FundamentalSnapshot.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return FundamentalSnapshotDTO(
            symbol=row.symbol,
            exchange=row.exchange,
            roe=row.roe,
            roce=row.roce,
            eps=row.eps,
            sales_growth_3y=row.sales_growth_3y,
            profit_growth_3y=row.profit_growth_3y,
            debt_to_equity=row.debt_to_equity,
            promoter_holding=row.promoter_holding,
            market_cap=row.market_cap,
            pe_ratio=row.pe_ratio,
            sector=row.sector,
            industry=row.industry,
        )

    async def get_market_cycle(self) -> MarketCycleDTO | None:
        row = (
            await self.session.execute(
                select(MarketCycleState)
                .order_by(MarketCycleState.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return MarketCycleDTO(
            regime=str(row.regime),
            nifty_roc_18m=row.nifty_roc_18m,
            smallcap_roc_20m=row.smallcap_roc_20m,
            suggested_allocation_pct=row.suggested_allocation_pct,
        )

    async def emit(self, candidate: ScanCandidate) -> None:
        self._emitted.append(candidate)


@dataclass
class ScannerRunner:
    session: AsyncSession

    async def run_one(self, config: ScannerConfig) -> int:
        """Run a single scanner config; returns count of persisted results."""
        try:
            cls = get_scanner_class(config.scanner_class)
        except KeyError:
            logger.warning(
                "scanner.unknown_class", scanner_id=str(config.id), cls=config.scanner_class,
            )
            return 0

        scanner: Scanner = cls(
            id=config.id, account_id=config.account_id, parameters=config.parameters or {},
        )
        run_ts = utcnow()
        ctx = _DbScanContext(
            session=self.session,
            account_id=config.account_id,
            scanner_id=config.id,
            run_ts=run_ts,
            _emitted=[],
        )
        await scanner.on_start(ctx)
        try:
            candidates = await scanner.scan(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scanner.scan_failed", scanner_id=str(config.id), error=str(exc))
            return 0
        finally:
            await scanner.on_stop(ctx)

        all_cands = list(ctx._emitted) + list(candidates)
        for cand in all_cands:
            score = max(0.0, min(1.0, float(cand.score)))
            row = ScanResult(
                scanner_id=config.id,
                run_ts=run_ts,
                symbol=cand.symbol,
                exchange=cand.exchange,
                score=Decimal(f"{score:.3f}"),
                stage=cand.stage or None,
                reason=cand.reason or None,
                suggested_entry=cand.suggested_entry,
                suggested_stop=cand.suggested_stop,
                suggested_target=cand.suggested_target,
                metadata_jsonb=cand.metadata or {},
                status=ScanResultStatus.NEW,
            )
            self.session.add(row)

        config.last_run_at = run_ts
        await self.session.commit()
        logger.info(
            "scanner.run_complete",
            scanner_id=str(config.id),
            count=len(all_cands),
        )
        return len(all_cands)

    async def run_all_enabled(self) -> int:
        configs = (
            await self.session.execute(
                select(ScannerConfig).where(
                    ScannerConfig.is_enabled.is_(True),
                    ScannerConfig.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        total = 0
        for cfg in configs:
            total += await self.run_one(cfg)
        return total
