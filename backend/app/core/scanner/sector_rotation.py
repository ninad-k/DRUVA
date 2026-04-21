"""Sector-rotation detector.

Heuristic: when the broad index (Nifty50) is sideways but individual stocks
print all-time highs, it signals rotation — stock-pickers market. Used as
a +0.2 score boost in the VCP scanner when regime=="neutral".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.ohlcv_repository import OhlcvRepository
from app.strategies.indicators.breadth import is_at_ath


@dataclass
class SectorRotationDetector:
    session: AsyncSession

    async def stock_at_ath(
        self, *, symbol: str, exchange: str = "NSE", lookback: int = 252,
    ) -> bool:
        repo = OhlcvRepository(session=self.session)
        candles = await repo.latest(
            symbol=symbol, exchange=exchange, timeframe="1d", limit=lookback + 5,
        )
        return is_at_ath(candles, lookback=lookback)
