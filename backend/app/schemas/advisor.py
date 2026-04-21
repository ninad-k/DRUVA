"""Pydantic schemas for the AI advisor REST surface."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class LLMConfigIn(BaseModel):
    provider: Literal["none", "anthropic", "openai", "ollama", "openai_compatible"]
    model: str = Field(min_length=1, max_length=128)
    base_url: str = Field(default="", max_length=512)
    api_key: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=32, le=8192)
    is_enabled: bool = True


class LLMConfigOut(BaseModel):
    id: UUID
    provider: str
    model: str
    base_url: str
    has_api_key: bool
    temperature: float
    max_tokens: int
    is_enabled: bool
    updated_at: datetime


class WatchlistIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    exchange: str = Field(default="NSE", max_length=8)
    sector: str | None = None
    notes: str | None = None  # JSON blob carrying fundamentals


class WatchlistOut(BaseModel):
    id: UUID
    symbol: str
    exchange: str
    sector: str | None
    notes: str | None
    is_active: bool


class ScoreOut(BaseModel):
    symbol: str
    exchange: str
    last_price: float | None
    composite_score: float
    fundamental_score: float
    technical_score: float
    momentum_score: float
    llm_score: float | None
    multibagger_tier: str | None
    stop_loss: float | None
    target_price: float | None
    suggested_allocation_pct: float
    rationale: str | None
    features: dict[str, Any]


class RunOut(BaseModel):
    id: UUID
    ran_at: datetime
    macro_regime: str
    nifty_roc: float | None
    smallcap_roc: float | None
    llm_provider: str | None
    llm_model: str | None
    symbols_scanned: int


class RunTriggerIn(BaseModel):
    capital_inr: float = Field(default=100_000.0, gt=0)
    max_positions: int = Field(default=8, ge=1, le=20)
    stop_loss_pct: float = Field(default=10.0, gt=0, le=50)


class AllocationOut(BaseModel):
    symbol: str
    exchange: str
    tier: str
    suggested_pct: float
    suggested_inr: float
    qty: int
    stop_loss: float
    target_price: float
