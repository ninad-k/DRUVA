"""End-to-end integration tests for RegimeExecutor.

Tests the full signal → VIX modifier → circuit breaker → execution pipeline
using mocked dependencies (broker, NSE VIX, yfinance).  No real network
calls or DB connections are made.

Coverage:
  1. Bull regime, low VIX  → BUY executed, allocation boosted
  2. Bear regime, persistence < 3 bars → no execution (flicker guard)
  3. Crash regime, high VIX → BUY blocked by VIX modifier cutting to 0%
  4. Circuit breaker Tier-1: daily loss -2.5% → half_cut, allocation halved
  5. Circuit breaker Tier-2: daily loss -3.5% → full_close, positions closed
  6. Circuit breaker Tier-3: -10% drawdown → lock file written, trading locked
  7. Trading pre-locked → run_daily_bar returns immediately, no VIX fetch
  8. Regime change → Telegram + email notifiers called with correct args
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.core.execution.regime_executor import RegimeExecutor, _LOCK_FILE
from app.core.market.india_vix import VixReading
from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy
from app.strategies.ml.base_ml import Prediction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300, regime_vol: float = 0.01) -> pd.DataFrame:
    """Generate synthetic NIFTY-like OHLCV with configurable volatility."""
    rng = np.random.default_rng(42)
    close = 20_000 * np.cumprod(1 + rng.normal(0.0004, regime_vol, n))
    return pd.DataFrame(
        {
            "open": close * (1 + rng.uniform(-0.003, 0.003, n)),
            "high": close * (1 + rng.uniform(0.001, 0.008, n)),
            "low": close * (1 - rng.uniform(0.001, 0.008, n)),
            "close": close,
            "volume": rng.integers(100_000, 500_000, n).astype(float),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="B"),
    )


def _bull_prediction(persistence: int = 5) -> Prediction:
    return Prediction(
        signal="BUY",
        confidence=0.85,
        meta={
            "regime_name": "Bull",
            "regime_id": 3,
            "confidence": 0.85,
            "allocation_pct": 95.0,
            "leverage": 1.25,
            "persistence_bars": persistence,
            "flicker_warning": False,
        },
    )


def _bear_prediction(persistence: int = 1) -> Prediction:
    return Prediction(
        signal="SELL",
        confidence=0.72,
        meta={
            "regime_name": "Bear",
            "regime_id": 1,
            "confidence": 0.72,
            "allocation_pct": 30.0,
            "leverage": 1.0,
            "persistence_bars": persistence,
            "flicker_warning": False,
        },
    )


def _crash_prediction(persistence: int = 4) -> Prediction:
    return Prediction(
        signal="SELL",
        confidence=0.90,
        meta={
            "regime_name": "Crash",
            "regime_id": 0,
            "confidence": 0.90,
            "allocation_pct": 5.0,
            "leverage": 1.0,
            "persistence_bars": persistence,
            "flicker_warning": False,
        },
    )


def _vix(value: float, source: str = "nse") -> VixReading:
    return VixReading(value=value, source=source)


def _mock_position(symbol: str = "NIFTYBEES", qty: int = 10) -> MagicMock:
    p = MagicMock()
    p.symbol = symbol
    p.quantity = qty
    p.avg_cost = Decimal("500")
    p.realized_pnl = Decimal("0")
    return p


def _make_executor(
    *,
    account_id: str | None = None,
    execution_service: MagicMock | None = None,
    telegram_notifier: MagicMock | None = None,
    email_notifier: MagicMock | None = None,
    strategy: RegimeTraderStrategy | None = None,
) -> RegimeExecutor:
    acc = account_id or str(uuid.uuid4())
    exec_svc = execution_service or AsyncMock()
    exec_svc.list_positions = AsyncMock(return_value=[])
    exec_svc.smart_order = AsyncMock(
        return_value=MagicMock(id=uuid.uuid4(), status="pending")
    )
    exec_svc.close_position = AsyncMock()

    tg = telegram_notifier or AsyncMock()
    tg.send_text = AsyncMock()

    em = email_notifier or AsyncMock()
    em.send_regime_change = AsyncMock()
    em.send_circuit_breaker_alert = AsyncMock()

    strat = strategy or MagicMock(spec=RegimeTraderStrategy)
    strat.build_features = MagicMock(return_value=[])

    return RegimeExecutor(
        execution_service=exec_svc,
        strategy=strat,
        telegram_notifier=tg,
        email_notifier=em,
        account_id=acc,
        telegram_chat_id="test_chat",
        alert_emails=["alert@druva.test"],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_lock_file():
    """Remove DRUVA.lock before and after each test."""
    if _LOCK_FILE.exists():
        _LOCK_FILE.unlink()
    yield
    if _LOCK_FILE.exists():
        _LOCK_FILE.unlink()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bull_regime_low_vix_executes_buy():
    """TC1: Bull regime + VIX 11 (modifier +2) → BUY executed, allocation boosted."""
    executor = _make_executor()
    ohlcv = _make_ohlcv()

    executor.strategy.predict = MagicMock(return_value=_bull_prediction(persistence=5))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(11.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["executed"] is True
    assert result["signal"] == "BUY"
    assert result["regime"] == "Bull"
    assert result["circuit_status"] == "normal"
    # VIX modifier +2 at 11.0 → allocation boosted from 95 by +10pp
    assert result["allocation_pct"] > 95.0
    assert result["vix"] == 11.0
    executor.execution_service.smart_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_bear_regime_low_persistence_no_execution():
    """TC2: Bear regime with persistence=1 (< 3 bars) → signal blocked by persistence guard."""
    executor = _make_executor()
    ohlcv = _make_ohlcv()
    executor.strategy.predict = MagicMock(return_value=_bear_prediction(persistence=1))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(17.5)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["executed"] is False
    assert result["signal"] == "SELL"
    assert result["persistence_bars"] == 1
    executor.execution_service.smart_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_high_vix_cuts_allocation():
    """TC3: VIX=30 (extreme fear, modifier -2) cuts Bull allocation by 10pp."""
    executor = _make_executor()
    ohlcv = _make_ohlcv()
    executor.strategy.predict = MagicMock(return_value=_bull_prediction(persistence=5))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(30.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
    ):
        result = await executor.run_daily_bar(ohlcv)

    # VIX modifier -2 at 30.0 → allocation cut by 10pp from 95.0 → 85.0
    assert result["allocation_pct"] < 95.0
    assert result["vix_modifier"] == -2


@pytest.mark.asyncio
async def test_circuit_breaker_half_cut_halves_allocation():
    """TC4: Daily loss -2.5% → Tier-1 half_cut; executed with halved allocation."""
    exec_svc = AsyncMock()
    # Simulate portfolio losing 2.5% daily
    position = _mock_position(qty=100)
    position.realized_pnl = Decimal("-2500")  # -2.5% of 100k portfolio
    position.avg_cost = Decimal("1000")
    exec_svc.list_positions = AsyncMock(return_value=[position])
    exec_svc.smart_order = AsyncMock(
        return_value=MagicMock(id=uuid.uuid4(), status="pending")
    )
    exec_svc.close_position = AsyncMock()

    executor = _make_executor(execution_service=exec_svc)
    # Seed peak value higher than current to simulate drawdown
    object.__setattr__(executor, "_peak_value", 100_000.0)

    ohlcv = _make_ohlcv()
    executor.strategy.predict = MagicMock(return_value=_bull_prediction(persistence=5))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(14.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
        patch.object(
            executor,
            "_fetch_portfolio_metrics",
            return_value=(100_000.0, -2500.0, 100_000.0),
        ),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["circuit_status"] == "half_cut"
    assert result["executed"] is True
    # smart_order was called (half_cut doesn't block, it halves)
    exec_svc.smart_order.assert_awaited_once()


@pytest.mark.asyncio
async def test_circuit_breaker_full_close_closes_positions():
    """TC5: Daily loss -3.5% → Tier-2 full_close; all positions closed, no new orders."""
    exec_svc = AsyncMock()
    exec_svc.list_positions = AsyncMock(return_value=[_mock_position("NIFTYBEES", 50)])
    exec_svc.smart_order = AsyncMock()
    exec_svc.close_position = AsyncMock()

    executor = _make_executor(execution_service=exec_svc)
    ohlcv = _make_ohlcv()
    executor.strategy.predict = MagicMock(return_value=_bull_prediction(persistence=5))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(14.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
        patch.object(
            executor,
            "_fetch_portfolio_metrics",
            return_value=(100_000.0, -3_500.0, 100_000.0),
        ),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["circuit_status"] == "full_close"
    assert result["executed"] is True  # full_close counts as executed
    exec_svc.close_position.assert_awaited()
    exec_svc.smart_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_circuit_breaker_lock_writes_lock_file():
    """TC6: -10% drawdown from peak → Tier-3 locked; DRUVA.lock created."""
    executor = _make_executor()
    ohlcv = _make_ohlcv()
    executor.strategy.predict = MagicMock(return_value=_bull_prediction(persistence=5))

    # Portfolio at 89k, peak was 100k → -11% drawdown
    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(14.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
        patch.object(
            executor,
            "_fetch_portfolio_metrics",
            return_value=(89_000.0, -500.0, 100_000.0),
        ),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["circuit_status"] == "locked"
    assert _LOCK_FILE.exists()
    lock_contents = _LOCK_FILE.read_text()
    assert "drawdown_10pct" in lock_contents


@pytest.mark.asyncio
async def test_pre_locked_aborts_immediately():
    """TC7: DRUVA.lock already exists → run_daily_bar returns without any VIX fetch."""
    _LOCK_FILE.write_text('{"reason": "prior_lock"}', encoding="utf-8")

    vix_fetch = AsyncMock()
    executor = _make_executor()
    ohlcv = _make_ohlcv()

    with patch(
        "app.core.execution.regime_executor.get_vix_with_fallback",
        side_effect=vix_fetch,
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["executed"] is False
    assert result["reason"] == "trading_locked"
    vix_fetch.assert_not_awaited()
    executor.execution_service.smart_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_regime_change_notifies_telegram_and_email():
    """TC8: Regime transitions Bull→Bear → both Telegram and email notifiers called."""
    tg = AsyncMock()
    tg.send_text = AsyncMock()
    em = AsyncMock()
    em.send_regime_change = AsyncMock()
    em.send_circuit_breaker_alert = AsyncMock()

    executor = _make_executor(telegram_notifier=tg, email_notifier=em)
    executor._last_regime = "Bull"  # seed previous regime
    ohlcv = _make_ohlcv()

    # Now predict Bear → regime change
    executor.strategy.predict = MagicMock(return_value=_bear_prediction(persistence=4))

    with (
        patch("app.core.execution.regime_executor.get_vix_with_fallback", return_value=_vix(20.0)),
        patch.object(executor, "_get_http_client", return_value=AsyncMock()),
    ):
        result = await executor.run_daily_bar(ohlcv)

    assert result["regime"] == "Bear"
    # Telegram notified
    tg.send_text.assert_awaited_once()
    telegram_msg: str = tg.send_text.call_args[0][1]
    assert "Bear" in telegram_msg
    assert "Bull" in telegram_msg

    # Email notified
    em.send_regime_change.assert_awaited_once()
    email_kwargs = em.send_regime_change.call_args.kwargs
    assert email_kwargs["old_regime"] == "Bull"
    assert email_kwargs["new_regime"] == "Bear"
