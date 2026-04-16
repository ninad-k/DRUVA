"""Shared streaming DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Tick:
    """A single market-data tick. Brokers normalise into this shape before
    handing off to the StreamHub."""

    symbol: str
    exchange: str
    last_price: Decimal
    last_quantity: Decimal
    ts: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume: Decimal | None = None
