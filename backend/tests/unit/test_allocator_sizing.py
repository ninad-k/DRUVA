from __future__ import annotations

from decimal import Decimal
from math import floor

import pytest


def _expected_qty(
    capital: Decimal, per_pos_pct: float, cycle_pct: float, score: float, price: Decimal, lot: int,
) -> Decimal:
    base = capital * (Decimal(str(per_pos_pct)) / Decimal("100"))
    cyc = Decimal(str(cycle_pct)) / Decimal("100")
    conf = Decimal(str(score))
    target = base * cyc * conf
    raw = target / price
    qty = Decimal(floor(raw / max(lot, 1))) * Decimal(max(lot, 1))
    return qty


@pytest.mark.unit
def test_sizing_formula_rounds_to_lot_size() -> None:
    capital = Decimal("1000000")
    # 5% base * 60% cycle * 0.8 score = 2.4% notional = 24,000 / 100 = 240 shares → lot 10 → 240
    qty = _expected_qty(capital, 5.0, 60.0, 0.8, Decimal("100"), 10)
    assert qty == Decimal("240")


@pytest.mark.unit
def test_sizing_zero_when_below_lot() -> None:
    capital = Decimal("100000")
    qty = _expected_qty(capital, 5.0, 60.0, 0.2, Decimal("1000"), 50)
    assert qty == Decimal("0")


@pytest.mark.unit
def test_sizing_bull_regime_bigger_than_bear() -> None:
    capital = Decimal("1000000")
    bull = _expected_qty(capital, 5.0, 90.0, 1.0, Decimal("100"), 1)
    bear = _expected_qty(capital, 5.0, 30.0, 1.0, Decimal("100"), 1)
    assert bull > bear
