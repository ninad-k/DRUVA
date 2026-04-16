from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_execution_service
from app.core.auth.dependencies import get_current_user
from app.core.execution.execution_service import ExecutionService
from app.db.models.user import User
from app.schemas.order import (
    BasketOrderPayload,
    ModifyOrderPayload,
    OrderResponse,
    PlaceOrderPayload,
    PositionResponse,
    SmartOrderPayload,
)

router = APIRouter()


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: PlaceOrderPayload,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> OrderResponse:
    order = await service.place_order(str(user.id), payload)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/orders/smart", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def smart_order(
    payload: SmartOrderPayload,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> OrderResponse:
    order = await service.smart_order(str(user.id), payload)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/orders/basket", response_model=list[OrderResponse], status_code=status.HTTP_201_CREATED)
async def basket_order(
    payload: BasketOrderPayload,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> list[OrderResponse]:
    orders = await service.basket_order(str(user.id), payload)
    return [OrderResponse.model_validate(order, from_attributes=True) for order in orders]


@router.post("/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> OrderResponse:
    order = await service.cancel_order(str(user.id), order_id)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.post("/accounts/{account_id}/orders/cancel-all", response_model=list[OrderResponse])
async def cancel_all(
    account_id: UUID,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> list[OrderResponse]:
    orders = await service.cancel_all(str(user.id), account_id)
    return [OrderResponse.model_validate(order, from_attributes=True) for order in orders]


@router.post("/accounts/{account_id}/positions/{symbol}/close", response_model=OrderResponse)
async def close_position(
    account_id: UUID,
    symbol: str,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> OrderResponse:
    order = await service.close_position(str(user.id), account_id, symbol)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.patch("/orders/{order_id}", response_model=OrderResponse)
async def modify_order(
    order_id: UUID,
    payload: ModifyOrderPayload,
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> OrderResponse:
    order = await service.modify_order(str(user.id), order_id, payload)
    return OrderResponse.model_validate(order, from_attributes=True)


@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    account_id: UUID = Query(...),
    user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> list[OrderResponse]:
    orders = await service.list_orders(str(user.id), account_id)
    return [OrderResponse.model_validate(order, from_attributes=True) for order in orders]


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    account_id: UUID = Query(...),
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(get_execution_service),
) -> list[PositionResponse]:
    positions = await service.list_positions(account_id)
    return [PositionResponse.model_validate(position, from_attributes=True) for position in positions]
