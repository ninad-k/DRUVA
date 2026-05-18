import datetime

from dhruva.v1 import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Order(_message.Message):
    __slots__ = ("id", "account_id", "symbol", "exchange", "side", "order_type", "quantity", "price", "trigger_price", "status", "broker_order_id", "filled_quantity", "filled_price", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_PRICE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    BROKER_ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    FILLED_QUANTITY_FIELD_NUMBER: _ClassVar[int]
    FILLED_PRICE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    account_id: str
    symbol: str
    exchange: _common_pb2.Exchange
    side: _common_pb2.Side
    order_type: _common_pb2.OrderType
    quantity: str
    price: str
    trigger_price: str
    status: _common_pb2.OrderStatus
    broker_order_id: str
    filled_quantity: str
    filled_price: str
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., account_id: _Optional[str] = ..., symbol: _Optional[str] = ..., exchange: _Optional[_Union[_common_pb2.Exchange, str]] = ..., side: _Optional[_Union[_common_pb2.Side, str]] = ..., order_type: _Optional[_Union[_common_pb2.OrderType, str]] = ..., quantity: _Optional[str] = ..., price: _Optional[str] = ..., trigger_price: _Optional[str] = ..., status: _Optional[_Union[_common_pb2.OrderStatus, str]] = ..., broker_order_id: _Optional[str] = ..., filled_quantity: _Optional[str] = ..., filled_price: _Optional[str] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class PlaceOrderRequest(_message.Message):
    __slots__ = ("account_id", "symbol", "exchange", "side", "order_type", "quantity", "price", "trigger_price", "tag")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_PRICE_FIELD_NUMBER: _ClassVar[int]
    TAG_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    symbol: str
    exchange: _common_pb2.Exchange
    side: _common_pb2.Side
    order_type: _common_pb2.OrderType
    quantity: str
    price: str
    trigger_price: str
    tag: str
    def __init__(self, account_id: _Optional[str] = ..., symbol: _Optional[str] = ..., exchange: _Optional[_Union[_common_pb2.Exchange, str]] = ..., side: _Optional[_Union[_common_pb2.Side, str]] = ..., order_type: _Optional[_Union[_common_pb2.OrderType, str]] = ..., quantity: _Optional[str] = ..., price: _Optional[str] = ..., trigger_price: _Optional[str] = ..., tag: _Optional[str] = ...) -> None: ...

class CancelOrderRequest(_message.Message):
    __slots__ = ("order_id",)
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    def __init__(self, order_id: _Optional[str] = ...) -> None: ...

class ModifyOrderRequest(_message.Message):
    __slots__ = ("order_id", "quantity", "price", "trigger_price", "order_type")
    ORDER_ID_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_PRICE_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    order_id: str
    quantity: str
    price: str
    trigger_price: str
    order_type: _common_pb2.OrderType
    def __init__(self, order_id: _Optional[str] = ..., quantity: _Optional[str] = ..., price: _Optional[str] = ..., trigger_price: _Optional[str] = ..., order_type: _Optional[_Union[_common_pb2.OrderType, str]] = ...) -> None: ...

class ListOrdersRequest(_message.Message):
    __slots__ = ("account_id", "page", "status_filter")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PAGE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FILTER_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    page: _common_pb2.Page
    status_filter: _common_pb2.OrderStatus
    def __init__(self, account_id: _Optional[str] = ..., page: _Optional[_Union[_common_pb2.Page, _Mapping]] = ..., status_filter: _Optional[_Union[_common_pb2.OrderStatus, str]] = ...) -> None: ...

class ListOrdersResponse(_message.Message):
    __slots__ = ("orders", "page_info")
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    PAGE_INFO_FIELD_NUMBER: _ClassVar[int]
    orders: _containers.RepeatedCompositeFieldContainer[Order]
    page_info: _common_pb2.PageInfo
    def __init__(self, orders: _Optional[_Iterable[_Union[Order, _Mapping]]] = ..., page_info: _Optional[_Union[_common_pb2.PageInfo, _Mapping]] = ...) -> None: ...
