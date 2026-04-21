from __future__ import annotations

from decimal import Decimal

import pytest

from app.config import Settings
from app.core.scanner.market_cycle import classify


def _settings() -> Settings:
    return Settings(
        market_cycle_bull_pct=90.0,
        market_cycle_neutral_pct=60.0,
        market_cycle_bear_pct=30.0,
    )


@pytest.mark.unit
def test_classify_bull_when_both_positive_and_small_outperforms() -> None:
    s = _settings()
    r = classify(Decimal("10"), Decimal("15"), s)
    assert r.regime.value == "bull"
    assert r.suggested_allocation_pct == Decimal("90.0")


@pytest.mark.unit
def test_classify_neutral_when_nifty_up_but_smallcap_flat() -> None:
    s = _settings()
    r = classify(Decimal("5"), Decimal("-1"), s)
    assert r.regime.value == "neutral"


@pytest.mark.unit
def test_classify_bear_when_both_negative() -> None:
    s = _settings()
    r = classify(Decimal("-2"), Decimal("-5"), s)
    assert r.regime.value == "bear"
    assert r.suggested_allocation_pct == Decimal("30.0")


@pytest.mark.unit
def test_classify_neutral_when_missing_data() -> None:
    s = _settings()
    r = classify(None, None, s)
    assert r.regime.value == "neutral"
