import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Side(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SIDE_UNSPECIFIED: _ClassVar[Side]
    BUY: _ClassVar[Side]
    SELL: _ClassVar[Side]

class OrderType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_TYPE_UNSPECIFIED: _ClassVar[OrderType]
    MARKET: _ClassVar[OrderType]
    LIMIT: _ClassVar[OrderType]
    SL: _ClassVar[OrderType]
    SL_M: _ClassVar[OrderType]

class OrderStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ORDER_STATUS_UNSPECIFIED: _ClassVar[OrderStatus]
    PENDING: _ClassVar[OrderStatus]
    OPEN: _ClassVar[OrderStatus]
    FILLED: _ClassVar[OrderStatus]
    PARTIAL: _ClassVar[OrderStatus]
    REJECTED: _ClassVar[OrderStatus]
    CANCELLED: _ClassVar[OrderStatus]

class Exchange(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXCHANGE_UNSPECIFIED: _ClassVar[Exchange]
    NSE: _ClassVar[Exchange]
    BSE: _ClassVar[Exchange]
    NFO: _ClassVar[Exchange]
    BFO: _ClassVar[Exchange]
    MCX: _ClassVar[Exchange]
SIDE_UNSPECIFIED: Side
BUY: Side
SELL: Side
ORDER_TYPE_UNSPECIFIED: OrderType
MARKET: OrderType
LIMIT: OrderType
SL: OrderType
SL_M: OrderType
ORDER_STATUS_UNSPECIFIED: OrderStatus
PENDING: OrderStatus
OPEN: OrderStatus
FILLED: OrderStatus
PARTIAL: OrderStatus
REJECTED: OrderStatus
CANCELLED: OrderStatus
EXCHANGE_UNSPECIFIED: Exchange
NSE: Exchange
BSE: Exchange
NFO: Exchange
BFO: Exchange
MCX: Exchange

class Money(_message.Message):
    __slots__ = ("amount", "currency")
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    amount: str
    currency: str
    def __init__(self, amount: _Optional[str] = ..., currency: _Optional[str] = ...) -> None: ...

class Page(_message.Message):
    __slots__ = ("offset", "limit")
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    offset: int
    limit: int
    def __init__(self, offset: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class PageInfo(_message.Message):
    __slots__ = ("total", "offset", "limit")
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    total: int
    offset: int
    limit: int
    def __init__(self, total: _Optional[int] = ..., offset: _Optional[int] = ..., limit: _Optional[int] = ...) -> None: ...

class AuditMeta(_message.Message):
    __slots__ = ("created_at", "updated_at")
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...
