import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ReportType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REPORT_TYPE_UNSPECIFIED: _ClassVar[ReportType]
    STRATEGY_PERFORMANCE: _ClassVar[ReportType]
    PORTFOLIO_MONTHLY: _ClassVar[ReportType]
    PORTFOLIO_QUARTERLY: _ClassVar[ReportType]
    PORTFOLIO_ANNUAL: _ClassVar[ReportType]
    RISK: _ClassVar[ReportType]
    TAX_PNL: _ClassVar[ReportType]
    TRADE_JOURNAL: _ClassVar[ReportType]
    MULTI_ACCOUNT: _ClassVar[ReportType]

class ReportFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REPORT_FORMAT_UNSPECIFIED: _ClassVar[ReportFormat]
    PDF: _ClassVar[ReportFormat]
    EXCEL: _ClassVar[ReportFormat]
    CSV: _ClassVar[ReportFormat]
REPORT_TYPE_UNSPECIFIED: ReportType
STRATEGY_PERFORMANCE: ReportType
PORTFOLIO_MONTHLY: ReportType
PORTFOLIO_QUARTERLY: ReportType
PORTFOLIO_ANNUAL: ReportType
RISK: ReportType
TAX_PNL: ReportType
TRADE_JOURNAL: ReportType
MULTI_ACCOUNT: ReportType
REPORT_FORMAT_UNSPECIFIED: ReportFormat
PDF: ReportFormat
EXCEL: ReportFormat
CSV: ReportFormat

class Report(_message.Message):
    __slots__ = ("id", "user_id", "account_id", "strategy_id", "type", "period", "format", "file_url", "generated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    FILE_URL_FIELD_NUMBER: _ClassVar[int]
    GENERATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    user_id: str
    account_id: str
    strategy_id: str
    type: ReportType
    period: str
    format: ReportFormat
    file_url: str
    generated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., user_id: _Optional[str] = ..., account_id: _Optional[str] = ..., strategy_id: _Optional[str] = ..., type: _Optional[_Union[ReportType, str]] = ..., period: _Optional[str] = ..., format: _Optional[_Union[ReportFormat, str]] = ..., file_url: _Optional[str] = ..., generated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class GenerateReportRequest(_message.Message):
    __slots__ = ("account_id", "strategy_id", "type", "period", "format")
    ACCOUNT_ID_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    account_id: str
    strategy_id: str
    type: ReportType
    period: str
    format: ReportFormat
    def __init__(self, account_id: _Optional[str] = ..., strategy_id: _Optional[str] = ..., type: _Optional[_Union[ReportType, str]] = ..., period: _Optional[str] = ..., format: _Optional[_Union[ReportFormat, str]] = ...) -> None: ...

class ListReportsRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: _Optional[str] = ...) -> None: ...

class ListReportsResponse(_message.Message):
    __slots__ = ("reports",)
    REPORTS_FIELD_NUMBER: _ClassVar[int]
    reports: _containers.RepeatedCompositeFieldContainer[Report]
    def __init__(self, reports: _Optional[_Iterable[_Union[Report, _Mapping]]] = ...) -> None: ...
