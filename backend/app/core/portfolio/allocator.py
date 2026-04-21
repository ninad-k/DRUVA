"""Position sizing — confidence × market-cycle × per-position cap.

qty = floor(base_alloc * cycle_factor * conf_factor / price / lot_size) * lot_size

where:
- base_alloc     = capital_inr * (max_per_position_pct / 100)
- cycle_factor   = MarketCycleState.suggested_allocation_pct / 100
- conf_factor    = candidate.score (0..1)

capital_inr falls back to the broker's available cash (live) or a configured
paper default so the scanner still produces tradable sizes in dev.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import floor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.account import Account
from app.db.models.instrument import Instrument
from app.db.models.market_cycle import MarketCycleState


@dataclass
class PositionSizer:
    session: AsyncSession
    settings: Settings = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_settings()

    async def _cycle_factor(self) -> Decimal:
        row = (
            await self.session.execute(
                select(MarketCycleState)
                .order_by(MarketCycleState.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return Decimal(str(self.settings.market_cycle_neutral_pct)) / Decimal("100")
        return row.suggested_allocation_pct / Decimal("100")

    async def _lot_size(self, symbol: str, exchange: str, broker_id: str) -> int:
        inst = (
            await self.session.execute(
                select(Instrument).where(
                    Instrument.symbol == symbol,
                    Instrument.exchange == exchange,
                    Instrument.broker_id == broker_id,
                )
            )
        ).scalar_one_or_none()
        return inst.lot_size if inst else 1

    async def size(
        self,
        *,
        account: Account,
        symbol: str,
        exchange: str,
        score: float,
        price: Decimal,
        capital_inr: Decimal | None = None,
    ) -> tuple[Decimal, str | None]:
        if price <= 0:
            return Decimal("0"), "no_price"
        if capital_inr is None:
            capital_inr = Decimal("1000000")  # paper default: 10 lakh
        base_alloc = capital_inr * (Decimal(str(self.settings.max_per_position_pct)) / Decimal("100"))
        cycle = await self._cycle_factor()
        conf = Decimal(str(max(0.0, min(1.0, score))))
        target_notional = base_alloc * cycle * conf
        lot = await self._lot_size(symbol, exchange, account.broker_id)
        raw_qty = target_notional / price
        qty = Decimal(floor(raw_qty / max(lot, 1))) * Decimal(max(lot, 1))
        if qty <= 0:
            return Decimal("0"), "size_below_lot"
        return qty, None
