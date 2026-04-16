"""Master-contract sync.

For each broker, we:
1. Pick any active Account belonging to that broker (we need creds to call the API).
2. Stream the broker's instrument master via ``download_master_contract()``,
   which is an *async generator* — we iterate it, NOT await it.
3. UPSERT each record into the ``instruments`` table.
4. Update the ``master_contract_status`` row.
5. Audit the sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.factory import BrokerFactory
from app.core.audit.event_store import AuditService
from app.core.errors import NotFoundError
from app.db.models.account import Account
from app.db.models.instrument import Instrument, MasterContractStatus
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SyncResult:
    broker_id: str
    records: int
    status: str


@dataclass
class InstrumentSyncService:
    session: AsyncSession
    factory: BrokerFactory
    audit_service: AuditService

    async def sync_broker(self, broker_id: str) -> SyncResult:
        account = await self.session.scalar(
            select(Account).where(
                Account.broker_id == broker_id,
                Account.is_active.is_(True),
            )
        )
        if account is None:
            raise NotFoundError("no_active_account_for_broker")

        broker = await self.factory.create(account)

        count = 0
        try:
            # NOTE: download_master_contract is an async generator. Do NOT await
            # the call itself — iterate it directly.
            async for record in broker.download_master_contract():
                stmt = insert(Instrument).values(
                    symbol=record.symbol,
                    exchange=record.exchange,
                    broker_token=record.broker_token,
                    broker_id=broker_id,
                    instrument_type=record.instrument_type,
                    expiry=record.expiry,
                    strike=record.strike,
                    lot_size=record.lot_size,
                    tick_size=record.tick_size,
                    isin=record.isin,
                    trading_symbol=record.trading_symbol,
                    exchange_token=record.exchange_token,
                    extra_jsonb=record.extra,
                    updated_at=datetime.now(UTC),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["broker_id", "symbol", "exchange"],
                    set_={
                        "broker_token": stmt.excluded.broker_token,
                        "instrument_type": stmt.excluded.instrument_type,
                        "lot_size": stmt.excluded.lot_size,
                        "tick_size": stmt.excluded.tick_size,
                        "expiry": stmt.excluded.expiry,
                        "strike": stmt.excluded.strike,
                        "trading_symbol": stmt.excluded.trading_symbol,
                        "exchange_token": stmt.excluded.exchange_token,
                        "isin": stmt.excluded.isin,
                        "extra_jsonb": stmt.excluded.extra_jsonb,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await self.session.execute(stmt)
                count += 1
        except Exception as exc:  # noqa: BLE001
            await self._update_status(broker_id, status="failed", count=count, error=str(exc))
            await self.session.commit()
            logger.exception("instruments.sync_failed", broker_id=broker_id, error=str(exc))
            raise

        await self._update_status(broker_id, status="ok", count=count, error=None)
        await self.audit_service.record(
            action="instruments.synced",
            entity_type="Instrument",
            entity_id=broker_id,
            old_value=None,
            new_value={"records": count},
            user_id=str(account.user_id),
            ip=None,
            user_agent=None,
            session=self.session,
        )
        await self.session.commit()
        return SyncResult(broker_id=broker_id, records=count, status="ok")

    async def _update_status(
        self,
        broker_id: str,
        *,
        status: str,
        count: int,
        error: str | None,
    ) -> None:
        row = await self.session.scalar(
            select(MasterContractStatus).where(MasterContractStatus.broker_id == broker_id)
        )
        if row is None:
            row = MasterContractStatus(broker_id=broker_id)
            self.session.add(row)
        row.status = status
        row.last_synced_at = datetime.now(UTC)
        row.record_count = count
        row.error_message = error
