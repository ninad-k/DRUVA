from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PlaceOrderPayload(BaseModel):
    account_id: UUID
    symbol: str
    exchange: str
    side: Literal["BUY", "SELL"]
    quantity: Decimal
    order_type: Literal["MARKET", "LIMIT", "SL", "SL_M"]
    product: Literal["MIS", "CNC", "NRML"]
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    strategy_id: UUID | None = None
    tag: str | None = None

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("quantity_must_be_positive")
        return value


class SmartOrderPayload(BaseModel):
    account_id: UUID
    symbol: str
    exchange: str
    target_quantity: Decimal
    product: Literal["MIS", "CNC", "NRML"]
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    price: Decimal | None = None


class BasketOrderPayload(BaseModel):
    orders: list[PlaceOrderPayload]
    atomic: bool = False


class ModifyOrderPayload(BaseModel):
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: Literal["MARKET", "LIMIT", "SL", "SL_M"] | None = None


class OrderResponse(BaseModel):
    id: UUID
    account_id: UUID
    symbol: str
    exchange: str
    side: str
    quantity: Decimal
    order_type: str
    product: str
    status: str
    broker_order_id: str | None = None


class PositionResponse(BaseModel):
    id: UUID
    account_id: UUID
    symbol: str
    exchange: str
    quantity: Decimal
    avg_cost: Decimal
    realized_pnl: Decimal
