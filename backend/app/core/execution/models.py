from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PlaceOrderRequest(BaseModel):
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


class SmartOrderRequest(BaseModel):
    account_id: UUID
    symbol: str
    exchange: str
    target_quantity: Decimal
    product: Literal["MIS", "CNC", "NRML"]
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    price: Decimal | None = None


class BasketOrderItem(PlaceOrderRequest):
    pass


class BasketOrderRequest(BaseModel):
    orders: list[BasketOrderItem]
    atomic: bool = False


class ModifyOrderRequest(BaseModel):
    quantity: Decimal | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: Literal["MARKET", "LIMIT", "SL", "SL_M"] | None = None


class RiskCheckResult(BaseModel):
    passed: bool
    reason: str | None = None


class RiskValidationResult(BaseModel):
    passed: bool
    reason: str | None = None
