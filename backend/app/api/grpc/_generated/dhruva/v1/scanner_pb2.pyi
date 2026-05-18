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

class Pattern(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PATTERN_UNSPECIFIED: _ClassVar[Pattern]
    MOMENTUM: _ClassVar[Pattern]
    MEAN_REVERSION: _ClassVar[Pattern]
    BREAKOUT: _ClassVar[Pattern]
    REVERSAL: _ClassVar[Pattern]
PATTERN_UNSPECIFIED: Pattern
MOMENTUM: Pattern
MEAN_REVERSION: Pattern
BREAKOUT: Pattern
REVERSAL: Pattern

class ScanResult(_message.Message):
    __slots__ = ("symbol", "exchange", "pattern", "setup_score", "reason", "last_price", "change_pct", "detected_at")
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    PATTERN_FIELD_NUMBER: _ClassVar[int]
    SETUP_SCORE_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    LAST_PRICE_FIELD_NUMBER: _ClassVar[int]
    CHANGE_PCT_FIELD_NUMBER: _ClassVar[int]
    DETECTED_AT_FIELD_NUMBER: _ClassVar[int]
    symbol: str
    exchange: _common_pb2.Exchange
    pattern: Pattern
    setup_score: float
    reason: str
    last_price: str
    change_pct: str
    detected_at: _timestamp_pb2.Timestamp
    def __init__(self, symbol: _Optional[str] = ..., exchange: _Optional[_Union[_common_pb2.Exchange, str]] = ..., pattern: _Optional[_Union[Pattern, str]] = ..., setup_score: _Optional[float] = ..., reason: _Optional[str] = ..., last_price: _Optional[str] = ..., change_pct: _Optional[str] = ..., detected_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class RunScanRequest(_message.Message):
    __slots__ = ("patterns", "min_score", "limit")
    PATTERNS_FIELD_NUMBER: _ClassVar[int]
    MIN_SCORE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    patterns: _containers.RepeatedScalarFieldContainer[Pattern]
    min_score: float
    limit: int
    def __init__(self, patterns: _Optional[_Iterable[_Union[Pattern, str]]] = ..., min_score: _Optional[float] = ..., limit: _Optional[int] = ...) -> None: ...

class RunScanResponse(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[ScanResult]
    def __init__(self, results: _Optional[_Iterable[_Union[ScanResult, _Mapping]]] = ...) -> None: ...
