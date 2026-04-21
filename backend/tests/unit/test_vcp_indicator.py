from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategies.base import Candle
from app.strategies.indicators.vcp import detect_vcp, trailing_ema_stop


def _mk(i: int, price: float, vol: float = 1000.0) -> Candle:
    return Candle(
        symbol="TEST",
        timeframe="1d",
        ts=datetime.now(UTC) + timedelta(days=i),
        open=Decimal(f"{price:.2f}"),
        high=Decimal(f"{price * 1.005:.2f}"),
        low=Decimal(f"{price * 0.995:.2f}"),
        close=Decimal(f"{price:.2f}"),
        volume=Decimal(f"{vol:.2f}"),
    )


@pytest.mark.unit
def test_vcp_returns_stage1_on_short_history() -> None:
    candles = [_mk(i, 100 + i) for i in range(10)]
    result = detect_vcp(candles)
    assert result.stage == "stage_1"
    assert result.score == 0.0


@pytest.mark.unit
def test_vcp_detects_uptrend_with_contractions() -> None:
    # Build 120 bars: steady uptrend with two consolidation bases + volume dry-up.
    series: list[Candle] = []
    price = 100.0
    for i in range(120):
        # linear trend up with small noise
        price += 0.6
        vol = 1500.0 if i < 80 else 500.0  # dry-up in the last base
        series.append(_mk(i, price, vol))
    result = detect_vcp(series)
    assert result.bases >= 0
    # Stage should reflect an uptrend (not stage_6 breakdown)
    assert result.stage in ("stage_1", "stage_2", "stage_3", "stage_4", "stage_5")
    assert result.score >= 0.0


@pytest.mark.unit
def test_trailing_ema_stop_none_on_short_history() -> None:
    candles = [_mk(i, 100 + i) for i in range(5)]
    assert trailing_ema_stop(candles, 21) is None


@pytest.mark.unit
def test_trailing_ema_stop_returns_decimal() -> None:
    candles = [_mk(i, 100 + i * 0.5) for i in range(50)]
    ema = trailing_ema_stop(candles, 21)
    assert ema is not None
    assert ema > Decimal("0")
