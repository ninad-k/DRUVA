from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.strategies.base import Candle
from app.strategies.indicators.roc import resample_monthly, roc


def _daily(year: int, month: int, day: int, close: float) -> Candle:
    return Candle(
        symbol="NIFTY",
        timeframe="1d",
        ts=datetime(year, month, day, tzinfo=UTC),
        open=Decimal(str(close)),
        high=Decimal(str(close * 1.01)),
        low=Decimal(str(close * 0.99)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
    )


@pytest.mark.unit
def test_resample_monthly_compacts_to_one_row_per_month() -> None:
    candles = [
        _daily(2024, 1, 5, 100),
        _daily(2024, 1, 15, 110),
        _daily(2024, 2, 3, 112),
        _daily(2024, 2, 28, 115),
    ]
    monthly = resample_monthly(candles)
    assert len(monthly) == 2
    assert monthly[0].close == Decimal("110")  # Jan last close
    assert monthly[1].close == Decimal("115")  # Feb last close


@pytest.mark.unit
def test_roc_returns_none_when_insufficient_history() -> None:
    candles = [_daily(2024, m, 1, 100 + m) for m in range(1, 6)]
    monthly = resample_monthly(candles)
    assert roc(monthly, 18) is None


@pytest.mark.unit
def test_roc_matches_hand_calculation() -> None:
    # 21 months, close goes 100 -> 120 (linear). ROC(20) from candles[-21].close=100.
    candles = []
    y, m = 2022, 1
    price = 100.0
    for _ in range(21):
        candles.append(_daily(y, m, 28, price))
        price += 1.0
        m += 1
        if m > 12:
            m = 1
            y += 1
    monthly = resample_monthly(candles)
    # start = candles[0] with close=100, end = candles[-1] with close=120 → ROC=20%.
    result = roc(monthly, 20)
    assert result is not None
    assert abs(float(result) - 20.0) < 0.01
