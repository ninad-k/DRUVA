from __future__ import annotations

from collections import deque
from decimal import Decimal

import pandas as pd
import pandas_ta as ta

from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.registry import register_strategy


@register_strategy("template.momentum.v1")
class MomentumStrategy(Strategy):
    def __init__(self, *, id: str, account_id: str, parameters: dict | None = None):
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self._closes: deque[Decimal] = deque(maxlen=50)

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:  # noqa: ARG002
        self._closes.append(candle.close)
        if len(self._closes) < 20:
            return None
        close_series = pd.Series([float(c) for c in self._closes])
        ema5 = ta.ema(close_series, length=5)
        ema20 = ta.ema(close_series, length=20)
        rsi = ta.rsi(close_series, length=14)
        if ema5 is None or ema20 is None or rsi is None:
            return None

        if float(ema5.iloc[-1]) > float(ema20.iloc[-1]) and float(rsi.iloc[-1]) > 55:
            return Signal(symbol=candle.symbol, side="BUY", quantity=Decimal("1"), reason="momentum_buy")
        if float(ema5.iloc[-1]) < float(ema20.iloc[-1]) and float(rsi.iloc[-1]) < 45:
            return Signal(symbol=candle.symbol, side="SELL", quantity=Decimal("1"), reason="momentum_sell")
        return None
