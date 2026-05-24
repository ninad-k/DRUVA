"""REST endpoints for persona Council mode + DCF valuation + correlation sizing.

All endpoints respect the existing JWT auth dependency. The Council uses the
same ``PortfolioAdvisor`` instance as ``ai_advisor.py``; the fundamentals
provider is built from settings (``DHRUVA_FUNDAMENTALS_PROVIDER``).
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.advisor.council import Council, CouncilVerdict, PersonaVerdict
from app.core.advisor.personas import Persona, list_personas, resolve_persona
from app.core.advisor.valuation import (
    FundamentalsProvider,
    build_provider,
    three_stage_dcf,
)
from app.core.ai.portfolio_advisor import PortfolioAdvisor, PortfolioContext
from app.core.ai.sentiment_engine import SentimentEngine, SentimentReading
from app.core.auth.dependencies import get_current_user
from app.core.risk.correlation_sizer import (
    compute_correlation_sizing,
    correlation_multiplier,
    volatility_adjusted_limit,
)
from app.db.models.user import User
from app.db.session import get_session
from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PersonaOut(BaseModel):
    slug: str
    display_name: str
    style: str
    checklist: list[str] = Field(default_factory=list)


class AskAsRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    symbol: str | None = Field(default=None, description="Optional NSE/BSE symbol.")
    exchange: str = "NSE"


class PersonaSignalOut(BaseModel):
    persona_slug: str
    persona_display_name: str
    signal: str
    confidence: int
    reasoning: str
    answer: str
    risk_level: str


class CouncilRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    exchange: str = "NSE"
    question: str = Field(
        default="Should we own this stock in current market regime?",
        min_length=3,
        max_length=2000,
    )
    personas: list[str] | None = Field(
        default=None,
        description="Optional list of persona slugs. If omitted, all are run.",
    )


class CouncilOut(BaseModel):
    symbol: str
    consensus: str
    consensus_confidence: float
    vote_distribution: dict[str, int]
    verdicts: list[PersonaSignalOut]
    fundamentals: dict[str, Any]
    intrinsic_value: dict[str, Any] | None
    notes: str
    as_of: str


class DCFRequest(BaseModel):
    symbol: str
    exchange: str = "NSE"
    growth_stage1: float | None = None
    years_stage1: int | None = None
    growth_stage2: float | None = None
    years_stage2: int | None = None
    terminal_growth: float | None = None
    discount_rate: float | None = None
    margin_of_safety: float | None = None


class CorrelationSizingRequest(BaseModel):
    annualised_volatility: float = Field(..., ge=0.0, le=5.0)
    avg_correlation: float = Field(..., ge=-1.0, le=1.0)
    portfolio_value: float = Field(..., gt=0.0)
    current_position_value: float = Field(default=0.0, ge=0.0)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def _get_advisor() -> PortfolioAdvisor:
    try:
        return PortfolioAdvisor()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI advisor unavailable: no LLM key configured.",
        ) from exc


def _get_provider() -> FundamentalsProvider:
    return build_provider(session_factory=get_session)


async def _build_context(regime: str = "Neutral") -> PortfolioContext:
    """Build a portfolio context for the Council using the live sentiment reading.

    Mirrors the mock-portfolio used elsewhere in ``ai_advisor.py``; will be
    replaced with a DB-backed context when the live-portfolio wiring lands.
    """
    sentiment: SentimentReading | None = None
    try:
        async with httpx.AsyncClient() as client:
            sentiment = await SentimentEngine().compute(client, current_regime=regime)
    except Exception as exc:  # noqa: BLE001 — sentiment is optional
        logger.warning("council.sentiment_fetch_failed", error=str(exc))

    return PortfolioContext(
        regime=sentiment.regime if sentiment else regime,
        confidence=0.82,
        sentiment_score=sentiment.score if sentiment else 0.0,
        sentiment_label=sentiment.label if sentiment else "Neutral",
        total_value=2_500_000.0,
        positions=[],
        cash_pct=20.0,
        daily_pnl_pct=0.0,
        top_holdings=[],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/personas", response_model=list[PersonaOut], summary="List Council personas")
async def list_council_personas(_user: User = Depends(get_current_user)) -> list[PersonaOut]:
    return [_persona_out(p) for p in list_personas()]


@router.post(
    "/ask-as/{persona_slug}",
    response_model=PersonaSignalOut,
    summary="Ask a single investor persona",
)
async def ask_as_persona(
    persona_slug: str,
    payload: AskAsRequest,
    _user: User = Depends(get_current_user),
) -> PersonaSignalOut:
    persona = resolve_persona(persona_slug)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"Unknown persona: {persona_slug}")

    advisor = _get_advisor()
    provider = _get_provider()
    council = Council(advisor=advisor, fundamentals_provider=provider)
    fundamentals = (
        await provider.get(payload.symbol, payload.exchange) if payload.symbol else None
    )
    context = await _build_context()

    verdict: PersonaVerdict = await council.ask_as(
        persona=persona,
        question=payload.question,
        context=context,
        fundamentals=fundamentals,
    )
    return _verdict_out(verdict)


@router.post("/council", response_model=CouncilOut, summary="Run the full Council")
async def run_council(
    payload: CouncilRequest,
    _user: User = Depends(get_current_user),
) -> CouncilOut:
    advisor = _get_advisor()
    provider = _get_provider()
    council = Council(advisor=advisor, fundamentals_provider=provider)
    context = await _build_context()

    verdict: CouncilVerdict = await council.run_council(
        symbol=payload.symbol.upper(),
        question=payload.question,
        context=context,
        persona_slugs=payload.personas,
    )
    return CouncilOut(
        symbol=verdict.symbol,
        consensus=verdict.consensus,
        consensus_confidence=verdict.consensus_confidence,
        vote_distribution=verdict.vote_distribution,
        verdicts=[_verdict_out(v) for v in verdict.verdicts],
        fundamentals=verdict.fundamentals,
        intrinsic_value=verdict.intrinsic_value,
        notes=verdict.notes,
        as_of=utcnow().isoformat(),
    )


@router.post("/dcf", summary="Run a three-stage DCF using the configured fundamentals provider")
async def dcf_intrinsic_value(
    payload: DCFRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    provider = _get_provider()
    view = await provider.get(payload.symbol.upper(), payload.exchange.upper())
    if view is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No fundamentals available for {payload.symbol}. Configure a "
                "provider via DHRUVA_FUNDAMENTALS_PROVIDER and supporting env vars."
            ),
        )
    kwargs = {
        k: v
        for k, v in {
            "growth_stage1": payload.growth_stage1,
            "years_stage1": payload.years_stage1,
            "growth_stage2": payload.growth_stage2,
            "years_stage2": payload.years_stage2,
            "terminal_growth": payload.terminal_growth,
            "discount_rate": payload.discount_rate,
            "margin_of_safety": payload.margin_of_safety,
        }.items()
        if v is not None
    }
    result = three_stage_dcf(view, **kwargs)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Fundamentals view did not contain enough data to seed the DCF "
                "(missing net income / FCF history *and* a usable PE shortcut)."
            ),
        )
    return {
        "symbol": view.symbol,
        "exchange": view.exchange,
        "source": view.source,
        "intrinsic_value_total": result.intrinsic_value_total,
        "intrinsic_value_per_share": result.intrinsic_value_per_share,
        "margin_of_safety_pct": result.margin_of_safety_pct,
        "owner_earnings": result.owner_earnings,
        "maintenance_capex": result.maintenance_capex,
        "stage1_pv": result.stage1_pv,
        "stage2_pv": result.stage2_pv,
        "terminal_pv": result.terminal_pv,
        "inputs": result.inputs,
        "degraded": result.degraded,
    }


@router.post(
    "/risk/correlation-sizing",
    summary="Compute a volatility- and correlation-adjusted position cap",
)
async def correlation_sizing(
    payload: CorrelationSizingRequest,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    result = compute_correlation_sizing(
        annualised_volatility=payload.annualised_volatility,
        avg_correlation=payload.avg_correlation,
        portfolio_value=payload.portfolio_value,
        current_position_value=payload.current_position_value,
    )
    return {
        "annualised_volatility": result.annualised_volatility,
        "avg_correlation": result.avg_correlation,
        "base_cap_pct": result.base_cap_pct,
        "correlation_multiplier": result.correlation_multiplier,
        "adjusted_cap_pct": result.adjusted_cap_pct,
        "adjusted_cap_inr": result.adjusted_cap_inr,
        "remaining_room_inr": result.remaining_room_inr,
    }


@router.get(
    "/risk/buckets",
    summary="Inspect the volatility / correlation bucket tables (for UI tooltips)",
)
async def correlation_buckets(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    sample_vols = [0.1, 0.2, 0.4, 0.6, 1.2]
    sample_corrs = [-0.2, 0.0, 0.3, 0.5, 0.7, 0.9]
    return {
        "volatility": [
            {"annualised_vol": v, "cap_pct": volatility_adjusted_limit(v)} for v in sample_vols
        ],
        "correlation": [
            {"avg_correlation": c, "multiplier": correlation_multiplier(c)} for c in sample_corrs
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _persona_out(p: Persona) -> PersonaOut:
    return PersonaOut(
        slug=p.slug,
        display_name=p.display_name,
        style=p.style,
        checklist=list(p.checklist),
    )


def _verdict_out(v: PersonaVerdict) -> PersonaSignalOut:
    return PersonaSignalOut(
        persona_slug=v.persona.slug,
        persona_display_name=v.persona.display_name,
        signal=v.signal.signal,
        confidence=v.signal.confidence,
        reasoning=v.signal.reasoning,
        answer=v.raw.answer,
        risk_level=v.raw.risk_level,
    )
