from __future__ import annotations

from collections import deque
from decimal import Decimal

from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.registry import register_strategy


@register_strategy("template.breakout.v1")
class BreakoutStrategy(Strategy):
    def __init__(self, *, id: str, account_id: str, parameters: dict | None = None):
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self._highs: deque[Decimal] = deque(maxlen=20)
        self._lows: deque[Decimal] = deque(maxlen=20)

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:  # noqa: ARG002
        if len(self._highs) == self._highs.maxlen:
            channel_high = max(self._highs)
            channel_low = min(self._lows)
            if candle.close > channel_high:
                signal = Signal(symbol=candle.symbol, side="BUY", quantity=Decimal("1"), reason="donchian_high")
            elif candle.close < channel_low:
                signal = Signal(symbol=candle.symbol, side="SELL", quantity=Decimal("1"), reason="donchian_low")
            else:
                signal = None
        else:
            signal = None
        self._highs.append(candle.high)
        self._lows.append(candle.low)
        return signal
