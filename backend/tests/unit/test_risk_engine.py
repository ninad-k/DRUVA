"""Risk engine unit tests — focused on the fixes from this iteration:
real lot_size enforcement, real margin from broker, qty-freeze enforcement.

Uses ``AsyncMock`` for the SQLAlchemy session and Redis to keep tests fast and
deterministic. Integration tests against a real DB live in ``tests/integration/``.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.execution.risk_engine import RiskEngine


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_min_lot_respects_instrument_lot_size() -> None:
    """Quantity must be a multiple of the instrument's lot_size."""
    engine = RiskEngine(session=MagicMock(), redis=MagicMock())

    # NIFTY futures lot of 50 — 50 passes, 75 fails.
    assert (await engine.check_min_lot(Decimal("50"), 50)).passed
    assert not (await engine.check_min_lot(Decimal("75"), 50)).passed
    # Equity (lot_size=1) — anything >0 passes.
    assert (await engine.check_min_lot(Decimal("1"), 1)).passed
    # Negative or zero quantity is always rejected.
    assert not (await engine.check_min_lot(Decimal("0"), 1)).passed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_qty_freeze_blocks_above_limit() -> None:
    """A quantity above the freeze limit is rejected."""
    session = MagicMock()
    session.scalar = AsyncMock(return_value=SimpleNamespace(qty_freeze=Decimal("900")))
    engine = RiskEngine(session=session, redis=MagicMock())

    above = await engine.check_qty_freeze("NSE", "RELIANCE", Decimal("1000"))
    assert not above.passed
    assert above.reason == "qty_freeze_exceeded"

    session.scalar = AsyncMock(return_value=SimpleNamespace(qty_freeze=Decimal("900")))
    within = await engine.check_qty_freeze("NSE", "RELIANCE", Decimal("500"))
    assert within.passed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_margin_paper_account_always_passes() -> None:
    engine = RiskEngine(session=MagicMock(), redis=MagicMock())
    paper_account = SimpleNamespace(is_paper=True, id="acc-1")
    result = await engine.check_margin(paper_account, Decimal("9999999"))
    assert result.passed


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_margin_live_account_uses_broker_get_margin() -> None:
    """For a live account we MUST hit broker.get_margin() and respect the
    available_cash that comes back. The previous implementation hardcoded a
    ten-crore comparison and never called the broker."""
    engine = RiskEngine(session=MagicMock(), redis=MagicMock())
    live_account = SimpleNamespace(is_paper=False, id="acc-2")

    broker = MagicMock()
    broker.get_margin = AsyncMock(
        return_value=SimpleNamespace(available_cash=Decimal("50000"), used_margin=Decimal("0"), total=Decimal("50000"))
    )

    # Required notional 49 999 fits within 50 000 cash.
    ok = await engine.check_margin(live_account, Decimal("49999"), broker=broker)
    assert ok.passed
    broker.get_margin.assert_awaited_once()

    # Required notional 50 001 exceeds 50 000 cash → rejected.
    broker.get_margin.reset_mock()
    too_big = await engine.check_margin(live_account, Decimal("50001"), broker=broker)
    assert not too_big.passed
    assert too_big.reason == "insufficient_margin"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_margin_live_without_broker_or_factory_fails_safe() -> None:
    """If no broker is supplied AND no factory is wired, the check returns
    failure rather than silently passing — this guards against accidental
    misconfiguration disabling margin enforcement."""
    engine = RiskEngine(session=MagicMock(), redis=MagicMock(), broker_factory=None)
    live_account = SimpleNamespace(is_paper=False, id="acc-3")
    result = await engine.check_margin(live_account, Decimal("1000"))
    assert not result.passed
    assert result.reason == "margin_check_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_market_hours_holiday_blocks() -> None:
    session = MagicMock()
    session.scalar = AsyncMock(return_value=SimpleNamespace(holiday_date=None))
    engine = RiskEngine(session=session, redis=MagicMock())
    result = await engine.check_market_hours("NSE")
    assert not result.passed
    assert result.reason == "market_closed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_check_market_hours_no_sessions_defaults_open() -> None:
    """If no MarketSession rows are configured at all, default to open so dev
    environments aren't blocked. Production must seed the table."""
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)  # no holiday
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = []  # no sessions
    session.execute = AsyncMock(return_value=exec_result)
    engine = RiskEngine(session=session, redis=MagicMock())
    result = await engine.check_market_hours("NSE")
    assert result.passed
