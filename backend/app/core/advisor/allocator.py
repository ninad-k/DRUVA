"""Capital allocation engine.

Implements the transcript's rules:
- Concentrated portfolio (default 5–8 positions)
- 10% stop-loss cap per position
- Allocate more to higher-tier candidates
- Scale total deployed capital by macro regime multiplier

All rupees / quantities are plain Python floats; convert to ``Decimal`` at
the persistence boundary.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.advisor.macro import allocation_multiplier
from app.db.models.advisor import MacroRegime


@dataclass
class Candidate:
    symbol: str
    exchange: str
    composite_score: float
    tier: str
    last_price: float


@dataclass
class Allocation:
    symbol: str
    exchange: str
    tier: str
    suggested_pct: float        # of available capital
    suggested_inr: float
    qty: int
    stop_loss: float
    target_price: float


TIER_WEIGHT = {"S": 3.0, "A": 2.0, "B": 1.0, "C": 0.0}


def allocate(
    candidates: list[Candidate],
    *,
    capital_inr: float,
    regime: MacroRegime,
    max_positions: int = 8,
    stop_loss_pct: float = 10.0,
    target_multiple: float = 2.5,  # 2.5x => "multibagger" framing
) -> list[Allocation]:
    ranked = sorted(candidates, key=lambda c: c.composite_score, reverse=True)
    picked = [c for c in ranked if c.tier in ("S", "A", "B")][:max_positions]
    if not picked:
        return []

    total_weight = sum(TIER_WEIGHT[c.tier] for c in picked) or 1.0
    deploy = capital_inr * allocation_multiplier(regime)

    out: list[Allocation] = []
    for c in picked:
        pct = (TIER_WEIGHT[c.tier] / total_weight) * 100.0
        inr = deploy * (TIER_WEIGHT[c.tier] / total_weight)
        qty = int(inr // c.last_price) if c.last_price > 0 else 0
        sl = round(c.last_price * (1 - stop_loss_pct / 100.0), 2)
        tp = round(c.last_price * target_multiple, 2)
        out.append(Allocation(
            symbol=c.symbol,
            exchange=c.exchange,
            tier=c.tier,
            suggested_pct=round(pct, 2),
            suggested_inr=round(inr, 2),
            qty=qty,
            stop_loss=sl,
            target_price=tp,
        ))
    return out
