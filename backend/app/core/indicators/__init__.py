"""Unified indicator library — Phase K.

Native numpy implementations + pandas-ta bridge.

Quick start::

    from app.core.indicators import registry

    rsi_result = registry.compute("rsi", close=close_prices, length=14)
    print(rsi_result.value[-1])   # last RSI value

    bb = registry.compute("bbands", close=close_prices, length=20, std_dev=2.0)
    print(bb.arrays["upper"][-1], bb.arrays["lower"][-1])
"""

from app.core.indicators.base import IndicatorMeta, IndicatorResult
from app.core.indicators.registry import IndicatorRegistry, registry

__all__ = [
    "IndicatorMeta",
    "IndicatorRegistry",
    "IndicatorResult",
    "registry",
]
