"""Broker health monitor — verifies the persistent-counter fix.

The old implementation kept the failure counter in a local dict, so the
"3 consecutive failures → disable" rule never fired across runs. After the
fix, failures live on ``Account.consecutive_health_failures``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.brokers.health_monitor import FAILURES_BEFORE_DISABLE, BrokerHealthMonitor


def _make_account() -> SimpleNamespace:
    return SimpleNamespace(
        id="acc-1",
        broker_id="zerodha",
        is_active=True,
        consecutive_health_failures=0,
        health_disabled_at=None,
    )


def _session_returning(active: list, disabled: list) -> MagicMock:
    """Stub AsyncSession.execute returning two queries in sequence."""
    session = MagicMock()
    active_result = MagicMock()
    active_result.scalars.return_value.all.return_value = active
    disabled_result = MagicMock()
    disabled_result.scalars.return_value.all.return_value = disabled
    session.execute = AsyncMock(side_effect=[active_result, disabled_result])
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failures_persist_and_disable_after_threshold() -> None:
    account = _make_account()
    factory = MagicMock()
    broker = MagicMock()
    broker.health = AsyncMock(
        return_value=SimpleNamespace(is_healthy=False, latency_ms=1.0, message="down")
    )
    factory.create = AsyncMock(return_value=broker)

    # First run — one failure, still active.
    session = _session_returning([account], [])
    monitor = BrokerHealthMonitor(session=session, factory=factory)
    await monitor.run_once()
    assert account.consecutive_health_failures == 1
    assert account.is_active is True

    # Second run — two failures, still active.
    session = _session_returning([account], [])
    monitor = BrokerHealthMonitor(session=session, factory=factory)
    await monitor.run_once()
    assert account.consecutive_health_failures == 2
    assert account.is_active is True

    # Third run — threshold reached, account disabled, RiskAlert added.
    session = _session_returning([account], [])
    monitor = BrokerHealthMonitor(session=session, factory=factory)
    await monitor.run_once()
    assert account.consecutive_health_failures == FAILURES_BEFORE_DISABLE
    assert account.is_active is False
    assert account.health_disabled_at is not None
    session.add.assert_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recovery_re_enables_only_monitor_disabled_accounts() -> None:
    """A successful health check should re-enable an account ONLY if the
    monitor is the one that disabled it (``health_disabled_at`` is set)."""
    monitor_disabled = SimpleNamespace(
        id="acc-monitor",
        broker_id="zerodha",
        is_active=False,
        consecutive_health_failures=3,
        health_disabled_at=datetime.now(UTC),
    )
    admin_disabled = SimpleNamespace(
        id="acc-admin",
        broker_id="zerodha",
        is_active=False,
        consecutive_health_failures=0,
        health_disabled_at=None,
    )

    factory = MagicMock()
    broker = MagicMock()
    broker.health = AsyncMock(
        return_value=SimpleNamespace(is_healthy=True, latency_ms=1.0, message="ok")
    )
    factory.create = AsyncMock(return_value=broker)

    # The "active" set is empty (both are currently disabled). The monitor
    # also probes "disabled_by_monitor" accounts so it can recover them.
    session = _session_returning([], [monitor_disabled])
    monitor = BrokerHealthMonitor(session=session, factory=factory)
    await monitor.run_once()
    assert monitor_disabled.is_active is True
    assert monitor_disabled.health_disabled_at is None

    # Admin-disabled account is not in the disabled-by-monitor set so it
    # never gets probed; we don't accidentally re-enable it.
    assert admin_disabled.is_active is False
