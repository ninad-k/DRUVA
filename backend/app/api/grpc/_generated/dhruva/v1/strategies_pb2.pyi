import datetime

from dhruva.v1 import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StrategyMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STRATEGY_MODE_UNSPECIFIED: _ClassVar[StrategyMode]
    PAPER: _ClassVar[StrategyMode]
    LIVE: _ClassVar[StrategyMode]
STRATEGY_MODE_UNSPECIFIED: StrategyMode
PAPER: StrategyMode
LIVE: StrategyMode

class Strategy(_message.Message):
    __slots__ = ("id", "account_id", "name", "strategy_class", "parameters_json", "is_enabled", "is_ml", "model_version", "mode", "created_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_CLASS_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_JSON_FIELD_NUMBER: _ClassVar[int]
    IS_ENABLED_FIELD_NUMBER: _ClassVar[int]
    IS_ML_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    account_id: str
    name: str
    strategy_class: str
    parameters_json: str
    is_enabled: bool
    is_ml: bool
    model_version: str
    mode: StrategyMode
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., account_id: _Optional[str] = ..., name: _Optional[str] = ..., strategy_class: _Optional[str] = ..., parameters_json: _Optional[str] = ..., is_enabled: bool = ..., is_ml: bool = ..., model_version: _Optional[str] = ..., mode: _Optional[_Union[StrategyMode, str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateStrategyRequest(_message.Message):
    __slots__ = ("account_id", "name", "strategy_class", "parameters_json", "is_ml", "model_version", "mode")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_CLASS_FIELD_NUMBER: _ClassVar[int]
    PARAMETERS_JSON_FIELD_NUMBER: _ClassVar[int]
    IS_ML_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    name: str
    strategy_class: str
    parameters_json: str
    is_ml: bool
    model_version: str
    mode: StrategyMode
    def __init__(self, account_id: _Optional[str] = ..., name: _Optional[str] = ..., strategy_class: _Optional[str] = ..., parameters_json: _Optional[str] = ..., is_ml: bool = ..., model_version: _Optional[str] = ..., mode: _Optional[_Union[StrategyMode, str]] = ...) -> None: ...

class ListStrategiesRequest(_message.Message):
    __slots__ = ("account_id",)
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    def __init__(self, account_id: _Optional[str] = ...) -> None: ...

class ListStrategiesResponse(_message.Message):
    __slots__ = ("strategies",)
    STRATEGIES_FIELD_NUMBER: _ClassVar[int]
    strategies: _containers.RepeatedCompositeFieldContainer[Strategy]
    def __init__(self, strategies: _Optional[_Iterable[_Union[Strategy, _Mapping]]] = ...) -> None: ...

class ToggleStrategyRequest(_message.Message):
    __slots__ = ("strategy_id", "enabled")
    STRATEGY_ID_FIELD_NUMBER: _ClassVar[int]
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    strategy_id: str
    enabled: bool
    def __init__(self, strategy_id: _Optional[str] = ..., enabled: bool = ...) -> None: ...

class BacktestRequest(_message.Message):
    __slots__ = ("strategy_id", "from_ts", "to_ts", "symbols", "timeframe")
    STRATEGY_ID_FIELD_NUMBER: _ClassVar[int]
    FROM_TS_FIELD_NUMBER: _ClassVar[int]
    TO_TS_FIELD_NUMBER: _ClassVar[int]
    SYMBOLS_FIELD_NUMBER: _ClassVar[int]
    TIMEFRAME_FIELD_NUMBER: _ClassVar[int]
    strategy_id: str
    from_ts: _timestamp_pb2.Timestamp
    to_ts: _timestamp_pb2.Timestamp
    symbols: _containers.RepeatedScalarFieldContainer[str]
    timeframe: str
    def __init__(self, strategy_id: _Optional[str] = ..., from_ts: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., to_ts: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., symbols: _Optional[_Iterable[str]] = ..., timeframe: _Optional[str] = ...) -> None: ...

class BacktestResult(_message.Message):
    __slots__ = ("report_id", "metrics_json", "equity_curve_json", "trade_list_json")
    REPORT_ID_FIELD_NUMBER: _ClassVar[int]
    METRICS_JSON_FIELD_NUMBER: _ClassVar[int]
    EQUITY_CURVE_JSON_FIELD_NUMBER: _ClassVar[int]
    TRADE_LIST_JSON_FIELD_NUMBER: _ClassVar[int]
    report_id: str
    metrics_json: str
    equity_curve_json: str
    trade_list_json: str
    def __init__(self, report_id: _Optional[str] = ..., metrics_json: _Optional[str] = ..., equity_curve_json: _Optional[str] = ..., trade_list_json: _Optional[str] = ...) -> None: ...
