"""Broker health monitor.

Periodically pings each active account's broker. Failure counters live on the
``Account`` row, so the "3 consecutive failures → disable" rule works across
scheduled runs (a local dict would reset every invocation and never fire).

When an account is disabled by the monitor we stamp ``health_disabled_at``.
We only re-enable an account if the monitor was the one that disabled it; if
an admin or another subsystem turned it off, we leave it alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.factory import BrokerFactory
from app.db.models.account import Account
from app.db.models.notification import RiskAlert
from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

FAILURES_BEFORE_DISABLE = 3


@dataclass
class BrokerHealthMonitor:
    session: AsyncSession
    factory: BrokerFactory

    async def run_once(self) -> None:
        """Probe every account once and update its persistent failure counter."""
        accounts = (
            await self.session.execute(select(Account).where(Account.is_active.is_(True)))
        ).scalars().all()

        # Also probe accounts the monitor previously disabled, so we can re-enable
        # them on recovery without manual intervention.
        disabled_by_monitor = (
            await self.session.execute(
                select(Account).where(
                    Account.is_active.is_(False),
                    Account.health_disabled_at.is_not(None),
                )
            )
        ).scalars().all()

        for account in [*accounts, *disabled_by_monitor]:
            try:
                broker = await self.factory.create(account)
                health = await broker.health()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "broker.health.exception",
                    account_id=str(account.id),
                    broker=account.broker_id,
                    error=str(exc),
                )
                await self._record_failure(account)
                continue

            if health.is_healthy:
                await self._record_success(account)
            else:
                logger.warning(
                    "broker.health.unhealthy",
                    account_id=str(account.id),
                    broker=account.broker_id,
                    message=health.message,
                )
                await self._record_failure(account)

        await self.session.commit()

    async def _record_failure(self, account: Account) -> None:
        account.consecutive_health_failures += 1
        if (
            account.consecutive_health_failures >= FAILURES_BEFORE_DISABLE
            and account.is_active
        ):
            account.is_active = False
            account.health_disabled_at = utcnow()
            self.session.add(
                RiskAlert(
                    account_id=account.id,
                    severity="warning",
                    code="broker_health_down",
                    message=(
                        f"broker {account.broker_id} unhealthy for "
                        f"{account.consecutive_health_failures} consecutive checks; "
                        "live trading disabled"
                    ),
                )
            )

    async def _record_success(self, account: Account) -> None:
        had_failures = account.consecutive_health_failures > 0
        account.consecutive_health_failures = 0
        # Only re-enable if the monitor itself disabled the account. Respect any
        # admin/manual disable.
        if not account.is_active and account.health_disabled_at is not None:
            account.is_active = True
            account.health_disabled_at = None
            self.session.add(
                RiskAlert(
                    account_id=account.id,
                    severity="info",
                    code="broker_health_recovered",
                    message=f"broker {account.broker_id} recovered; live trading re-enabled",
                )
            )
        elif had_failures:
            logger.info(
                "broker.health.recovered",
                account_id=str(account.id),
                broker=account.broker_id,
            )
