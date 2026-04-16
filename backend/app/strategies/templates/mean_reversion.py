from __future__ import annotations

from collections import deque
from decimal import Decimal

import pandas as pd
import pandas_ta as ta

from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.registry import register_strategy


@register_strategy("template.mean_reversion.v1")
class MeanReversionStrategy(Strategy):
    def __init__(self, *, id: str, account_id: str, parameters: dict | None = None):
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self._closes: deque[Decimal] = deque(maxlen=30)

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:  # noqa: ARG002
        self._closes.append(candle.close)
        if len(self._closes) < 20:
            return None
        close_series = pd.Series([float(c) for c in self._closes])
        bands = ta.bbands(close_series, length=20, std=2)
        if bands is None:
            return None
        lower = float(bands.iloc[-1]["BBL_20_2.0"])
        upper = float(bands.iloc[-1]["BBU_20_2.0"])
        price = float(candle.close)
        if price <= lower:
            return Signal(symbol=candle.symbol, side="BUY", quantity=Decimal("1"), reason="bb_lower")
        if price >= upper:
            return Signal(symbol=candle.symbol, side="SELL", quantity=Decimal("1"), reason="bb_upper")
        return None
