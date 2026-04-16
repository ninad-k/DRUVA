from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class Exchange(str, enum.Enum):
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    MCX = "MCX"
    CDS = "CDS"
    BCD = "BCD"


class ProductType(str, enum.Enum):
    MIS = "MIS"
    CNC = "CNC"
    NRML = "NRML"


class OrderType(str, enum.Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL_M"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"


class InstrumentType(str, enum.Enum):
    EQ = "EQ"
    FUT = "FUT"
    CE = "CE"
    PE = "PE"
    IDX = "IDX"


class StrategyMode(str, enum.Enum):
    PAPER = "paper"
    LIVE = "live"


class SessionType(str, enum.Enum):
    REGULAR = "regular"
    PRE = "pre"
    POST = "post"


class MasterContractSyncStatus(str, enum.Enum):
    OK = "ok"
    STALE = "stale"
    FAILED = "failed"


class WebhookSourceType(str, enum.Enum):
    CHARTINK = "chartink"
    TRADINGVIEW = "tradingview"
    GOCHARTING = "gocharting"
    AMIBROKER = "amibroker"
    METATRADER = "metatrader"
    N8N = "n8n"


class WebhookEventStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


def enum_col(enum_type: type[enum.Enum], name: str) -> Enum:
    return Enum(enum_type, name=name, native_enum=False)
