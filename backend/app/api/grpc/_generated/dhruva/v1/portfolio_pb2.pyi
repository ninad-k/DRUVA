import datetime

from dhruva.v1 import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Position(_message.Message):
    __slots__ = ("account_id", "symbol", "exchange", "quantity", "avg_cost", "current_price", "market_value", "unrealized_pnl", "realized_pnl", "sector", "instrument_type", "updated_at")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    QUANTITY_FIELD_NUMBER: _ClassVar[int]
    AVG_COST_FIELD_NUMBER: _ClassVar[int]
    CURRENT_PRICE_FIELD_NUMBER: _ClassVar[int]
    MARKET_VALUE_FIELD_NUMBER: _ClassVar[int]
    UNREALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    REALIZED_PNL_FIELD_NUMBER: _ClassVar[int]
    SECTOR_FIELD_NUMBER: _ClassVar[int]
    INSTRUMENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    symbol: str
    exchange: _common_pb2.Exchange
    quantity: str
    avg_cost: str
    current_price: str
    market_value: str
    unrealized_pnl: str
    realized_pnl: str
    sector: str
    instrument_type: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, account_id: _Optional[str] = ..., symbol: _Optional[str] = ..., exchange: _Optional[_Union[_common_pb2.Exchange, str]] = ..., quantity: _Optional[str] = ..., avg_cost: _Optional[str] = ..., current_price: _Optional[str] = ..., market_value: _Optional[str] = ..., unrealized_pnl: _Optional[str] = ..., realized_pnl: _Optional[str] = ..., sector: _Optional[str] = ..., instrument_type: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class EquityPoint(_message.Message):
    __slots__ = ("ts", "equity", "daily_return")
    TS_FIELD_NUMBER: _ClassVar[int]
    EQUITY_FIELD_NUMBER: _ClassVar[int]
    DAILY_RETURN_FIELD_NUMBER: _ClassVar[int]
    ts: _timestamp_pb2.Timestamp
    equity: str
    daily_return: str
    def __init__(self, ts: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., equity: _Optional[str] = ..., daily_return: _Optional[str] = ...) -> None: ...

class Analytics(_message.Message):
    __slots__ = ("sharpe", "sortino", "calmar", "max_drawdown", "var_95", "cumulative_return", "volatility", "trade_count", "win_rate")
    SHARPE_FIELD_NUMBER: _ClassVar[int]
    SORTINO_FIELD_NUMBER: _ClassVar[int]
    CALMAR_FIELD_NUMBER: _ClassVar[int]
    MAX_DRAWDOWN_FIELD_NUMBER: _ClassVar[int]
    VAR_95_FIELD_NUMBER: _ClassVar[int]
    CUMULATIVE_RETURN_FIELD_NUMBER: _ClassVar[int]
    VOLATILITY_FIELD_NUMBER: _ClassVar[int]
    TRADE_COUNT_FIELD_NUMBER: _ClassVar[int]
    WIN_RATE_FIELD_NUMBER: _ClassVar[int]
    sharpe: str
    sortino: str
    calmar: str
    max_drawdown: str
    var_95: str
    cumulative_return: str
    volatility: str
    trade_count: int
    win_rate: float
    def __init__(self, sharpe: _Optional[str] = ..., sortino: _Optional[str] = ..., calmar: _Optional[str] = ..., max_drawdown: _Optional[str] = ..., var_95: _Optional[str] = ..., cumulative_return: _Optional[str] = ..., volatility: _Optional[str] = ..., trade_count: _Optional[int] = ..., win_rate: _Optional[float] = ...) -> None: ...

class GetPositionsRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    def __init__(self, account_id: _Optional[str] = ...) -> None: ...

class GetPositionsResponse(_message.Message):
    __slots__ = ("positions",)
    POSITIONS_FIELD_NUMBER: _ClassVar[int]
    positions: _containers.RepeatedCompositeFieldContainer[Position]
    def __init__(self, positions: _Optional[_Iterable[_Union[Position, _Mapping]]] = ...) -> None: ...

class GetEquityCurveRequest(_message.Message):
    __slots__ = ("account_id", "period")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    period: str
    def __init__(self, account_id: _Optional[str] = ..., period: _Optional[str] = ...) -> None: ...

class GetEquityCurveResponse(_message.Message):
    __slots__ = ("points",)
    POINTS_FIELD_NUMBER: _ClassVar[int]
    points: _containers.RepeatedCompositeFieldContainer[EquityPoint]
    def __init__(self, points: _Optional[_Iterable[_Union[EquityPoint, _Mapping]]] = ...) -> None: ...

class GetAnalyticsRequest(_message.Message):
    __slots__ = ("account_id", "period")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    period: str
    def __init__(self, account_id: _Optional[str] = ..., period: _Optional[str] = ...) -> None: ...
