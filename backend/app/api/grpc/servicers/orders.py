"""gRPC OrderService servicer implementation."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy import select

from app.api.grpc._generated.dhruva.v1 import common_pb2, orders_pb2, orders_pb2_grpc
from app.api.grpc.servicers._helpers import require_auth, ts_from_dt
from app.core.execution.execution_service import ExecutionService
from app.core.execution.models import (
    ModifyOrderRequest as SvcModifyReq,
    PlaceOrderRequest as SvcPlaceReq,
)
from app.db.models.common import Exchange, OrderSide, OrderStatus, OrderType
from app.db.models.order import Order
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Proto enum → domain string maps
_EXCHANGE_MAP = {
    common_pb2.Exchange.NSE: "NSE",
    common_pb2.Exchange.BSE: "BSE",
    common_pb2.Exchange.NFO: "NFO",
    common_pb2.Exchange.MCX: "MCX",
}
_SIDE_MAP = {common_pb2.Side.BUY: "BUY", common_pb2.Side.SELL: "SELL"}
_ORDER_TYPE_MAP = {
    common_pb2.OrderType.MARKET: "MARKET",
    common_pb2.OrderType.LIMIT: "LIMIT",
    common_pb2.OrderType.SL: "SL",
    common_pb2.OrderType.SL_M: "SL_M",
}

# Domain string → proto enum maps (reverse)
_STATUS_TO_PROTO = {
    "pending": common_pb2.OrderStatus.PENDING,
    "open": common_pb2.OrderStatus.OPEN,
    "filled": common_pb2.OrderStatus.FILLED,
    "partial": common_pb2.OrderStatus.PARTIAL,
    "rejected": common_pb2.OrderStatus.REJECTED,
    "cancelled": common_pb2.OrderStatus.CANCELLED,
}
_EXCHANGE_TO_PROTO = {v: k for k, v in _EXCHANGE_MAP.items()}
_SIDE_TO_PROTO = {v: k for k, v in _SIDE_MAP.items()}
_ORDER_TYPE_TO_PROTO = {v: k for k, v in _ORDER_TYPE_MAP.items()}


def _order_to_proto(order: Order) -> orders_pb2.Order:
    return orders_pb2.Order(
        id=str(order.id),
        account_id=str(order.account_id),
        symbol=order.symbol,
        exchange=_EXCHANGE_TO_PROTO.get(order.exchange.value if hasattr(order.exchange, "value") else str(order.exchange), common_pb2.Exchange.EXCHANGE_UNSPECIFIED),
        side=_SIDE_TO_PROTO.get(order.side.value if hasattr(order.side, "value") else str(order.side), common_pb2.Side.SIDE_UNSPECIFIED),
        order_type=_ORDER_TYPE_TO_PROTO.get(order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type), common_pb2.OrderType.ORDER_TYPE_UNSPECIFIED),
        quantity=str(order.quantity),
        price=str(order.price) if order.price is not None else "",
        trigger_price=str(order.trigger_price) if order.trigger_price is not None else "",
        status=_STATUS_TO_PROTO.get(order.status.value if hasattr(order.status, "value") else str(order.status), common_pb2.OrderStatus.ORDER_STATUS_UNSPECIFIED),
        broker_order_id=order.broker_order_id or "",
        filled_quantity=str(order.filled_quantity),
        filled_price="",  # not stored at order level
        created_at=ts_from_dt(order.created_at),
        updated_at=ts_from_dt(order.updated_at),
    )


class OrderServicer(orders_pb2_grpc.OrderServiceServicer):
    """Implements dhruva.v1.OrderService over gRPC."""

    async def PlaceOrder(self, request: orders_pb2.PlaceOrderRequest, context: grpc.aio.ServicerContext) -> orders_pb2.Order:
        user = await require_auth(context)
        async with SessionLocal() as session:
            try:
                from app.api.dependencies import build_execution_service_for_session
                svc = await build_execution_service_for_session(session)
                place_req = SvcPlaceReq(
                    account_id=UUID(request.account_id),
                    symbol=request.symbol,
                    exchange=_EXCHANGE_MAP.get(request.exchange, "NSE"),
                    side=_SIDE_MAP.get(request.side, "BUY"),
                    order_type=_ORDER_TYPE_MAP.get(request.order_type, "MARKET"),
                    product="MIS",
                    quantity=Decimal(request.quantity) if request.quantity else Decimal("1"),
                    price=Decimal(request.price) if request.price else None,
                    trigger_price=Decimal(request.trigger_price) if request.trigger_price else None,
                    tag=request.tag or None,
                )
                order = await svc.place_order(str(user.id), place_req)
                return _order_to_proto(order)
            except Exception as exc:
                logger.warning("grpc.orders.place_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def CancelOrder(self, request: orders_pb2.CancelOrderRequest, context: grpc.aio.ServicerContext) -> orders_pb2.Order:
        user = await require_auth(context)
        async with SessionLocal() as session:
            try:
                from app.api.dependencies import build_execution_service_for_session
                svc = await build_execution_service_for_session(session)
                order = await svc.cancel_order(str(user.id), UUID(request.order_id))
                return _order_to_proto(order)
            except Exception as exc:
                logger.warning("grpc.orders.cancel_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def ModifyOrder(self, request: orders_pb2.ModifyOrderRequest, context: grpc.aio.ServicerContext) -> orders_pb2.Order:
        user = await require_auth(context)
        async with SessionLocal() as session:
            try:
                from app.api.dependencies import build_execution_service_for_session
                svc = await build_execution_service_for_session(session)
                mod_req = SvcModifyReq(
                    quantity=Decimal(request.quantity) if request.quantity else None,
                    price=Decimal(request.price) if request.price else None,
                    trigger_price=Decimal(request.trigger_price) if request.trigger_price else None,
                    order_type=_ORDER_TYPE_MAP.get(request.order_type) if request.order_type else None,
                )
                order = await svc.modify_order(str(user.id), UUID(request.order_id), mod_req)
                return _order_to_proto(order)
            except Exception as exc:
                logger.warning("grpc.orders.modify_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def ListOrders(self, request: orders_pb2.ListOrdersRequest, context: grpc.aio.ServicerContext) -> orders_pb2.ListOrdersResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(Order).where(Order.account_id == UUID(request.account_id)).order_by(Order.created_at.desc())
                # Apply status filter if provided
                if request.status_filter and request.status_filter != common_pb2.OrderStatus.ORDER_STATUS_UNSPECIFIED:
                    status_str = next((k for k, v in _STATUS_TO_PROTO.items() if v == request.status_filter), None)
                    if status_str:
                        stmt = stmt.where(Order.status == status_str)
                # Pagination
                page_size = request.page.size if request.page and request.page.size > 0 else 50
                page_num = request.page.number if request.page and request.page.number > 0 else 1
                stmt = stmt.offset((page_num - 1) * page_size).limit(page_size)
                result = await session.execute(stmt)
                orders = result.scalars().all()
                return orders_pb2.ListOrdersResponse(
                    orders=[_order_to_proto(o) for o in orders],
                    page_info=common_pb2.PageInfo(total=len(orders), number=page_num, size=page_size),
                )
            except Exception as exc:
                logger.warning("grpc.orders.list_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))
