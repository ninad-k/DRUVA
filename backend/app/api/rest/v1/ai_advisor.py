"""REST API endpoints for the AI Portfolio Advisor."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.ai.portfolio_advisor import AdvisorResponse, PortfolioAdvisor, PortfolioContext
from app.core.ai.sentiment_engine import SentimentEngine, SentimentReading
from app.core.auth.dependencies import get_current_user
from app.db.models.user import User
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000, description="Portfolio question")


class EvaluateStockRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20, description="NSE/BSE ticker symbol")
    exchange: str = Field(default="NSE", description="Exchange: NSE or BSE")
    fundamentals: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional fundamental data (P/E, ROCE, EPS growth, etc.)",
    )


class AdvisorResponseOut(BaseModel):
    answer: str
    recommended_actions: list[str]
    risk_level: str
    confidence: float
    sources: list[str]


class SentimentOut(BaseModel):
    score: float
    label: str
    vix: float
    pcr: float
    fii_net_cr: float
    dii_net_cr: float
    advance_decline: float
    regime: str
    signals: dict[str, float]
    as_of: str


class RegimeStatusOut(BaseModel):
    regime: str
    confidence: float
    sentiment_score: float
    sentiment_label: str
    suggested_cash_pct: float
    suggested_equity_pct: float
    regime_description: str


class DailyBriefingOut(BaseModel):
    briefing: str
    regime: str
    sentiment_score: float
    sentiment_label: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Regime → suggested allocation (equity %, cash %)
_REGIME_ALLOCATION: dict[str, tuple[float, float]] = {
    "Crash":    (20.0,  80.0),
    "Bear":     (40.0,  60.0),
    "Neutral":  (65.0,  35.0),
    "Bull":     (85.0,  15.0),
    "Euphoria": (60.0,  40.0),  # reduce exposure at extremes
}

_REGIME_DESCRIPTIONS: dict[str, str] = {
    "Crash":    "Market in free-fall. Prioritise capital preservation. Limit equity exposure to blue-chips only.",
    "Bear":     "Sustained downtrend. Reduce speculative positions. Accumulate defensives on dips.",
    "Neutral":  "Mid-cycle consolidation. Standard allocation. Focus on quality stocks with earnings visibility.",
    "Bull":     "Healthy uptrend. Deploy capital in high-conviction ideas. Maintain stop-losses.",
    "Euphoria": "Overbought conditions. Trim winners, avoid chasing momentum. Build cash buffer.",
}


def _make_mock_portfolio_context(
    regime: str = "Neutral",
    sentiment: SentimentReading | None = None,
) -> PortfolioContext:
    """Build a realistic mock PortfolioContext for demo/stub usage.

    This will be replaced by actual DB queries once the portfolio models are
    wired up to this endpoint.
    """
    sentiment_score = sentiment.score if sentiment else 5.0
    sentiment_label = sentiment.label if sentiment else "Neutral"

    return PortfolioContext(
        regime=regime,
        confidence=0.82,
        sentiment_score=sentiment_score,
        sentiment_label=sentiment_label,
        total_value=2_500_000.0,
        positions=[
            {
                "symbol": "RELIANCE",
                "exchange": "NSE",
                "qty": 50,
                "avg_cost": 2_450.00,
                "ltp": 2_580.00,
                "pnl_pct": 5.31,
            },
            {
                "symbol": "HDFCBANK",
                "exchange": "NSE",
                "qty": 80,
                "avg_cost": 1_620.00,
                "ltp": 1_595.00,
                "pnl_pct": -1.54,
            },
            {
                "symbol": "INFY",
                "exchange": "NSE",
                "qty": 120,
                "avg_cost": 1_380.00,
                "ltp": 1_445.00,
                "pnl_pct": 4.71,
            },
            {
                "symbol": "TATAPOWER",
                "exchange": "NSE",
                "qty": 500,
                "avg_cost": 385.00,
                "ltp": 410.00,
                "pnl_pct": 6.49,
            },
            {
                "symbol": "ADANIGREEN",
                "exchange": "NSE",
                "qty": 60,
                "avg_cost": 1_950.00,
                "ltp": 1_820.00,
                "pnl_pct": -6.67,
            },
        ],
        cash_pct=18.5,
        daily_pnl_pct=0.73,
        top_holdings=[
            {"symbol": "RELIANCE",   "weight_pct": 9.8,  "pnl_pct": 5.31},
            {"symbol": "HDFCBANK",   "weight_pct": 9.2,  "pnl_pct": -1.54},
            {"symbol": "INFY",       "weight_pct": 8.7,  "pnl_pct": 4.71},
            {"symbol": "TATAPOWER",  "weight_pct": 7.4,  "pnl_pct": 6.49},
            {"symbol": "ADANIGREEN", "weight_pct": 6.1,  "pnl_pct": -6.67},
        ],
    )


def _get_advisor() -> PortfolioAdvisor:
    """Instantiate PortfolioAdvisor; raise 503 if API key is missing."""
    try:
        return PortfolioAdvisor()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI advisor unavailable: ANTHROPIC_API_KEY not configured.",
        ) from exc


def _sentiment_to_out(r: SentimentReading) -> SentimentOut:
    return SentimentOut(
        score=r.score,
        label=r.label,
        vix=r.vix,
        pcr=r.pcr,
        fii_net_cr=r.fii_net_cr,
        dii_net_cr=r.dii_net_cr,
        advance_decline=r.advance_decline,
        regime=r.regime,
        signals=r.signals,
        as_of=r.as_of.isoformat(),
    )


def _advisor_to_out(r: AdvisorResponse) -> AdvisorResponseOut:
    return AdvisorResponseOut(
        answer=r.answer,
        recommended_actions=r.recommended_actions,
        risk_level=r.risk_level,
        confidence=r.confidence,
        sources=r.sources,
    )


async def _get_current_sentiment(regime: str = "Neutral") -> SentimentReading:
    """Fetch live sentiment; returns a neutral fallback on any network error."""
    engine = SentimentEngine()
    async with httpx.AsyncClient() as client:
        try:
            return await engine.compute(client, current_regime=regime)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ai_advisor.sentiment_fetch_failed", error=str(exc))
            # Import the dataclass for inline fallback construction
            from app.core.ai.sentiment_engine import SentimentReading
            from app.utils.time import utcnow

            return SentimentReading(
                score=0.0,
                label="Neutral",
                vix=16.0,
                pcr=1.0,
                fii_net_cr=0.0,
                dii_net_cr=0.0,
                advance_decline=0.5,
                regime=regime,
                signals={},
                as_of=utcnow(),
            )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/ask", response_model=AdvisorResponseOut, summary="Ask the AI advisor a question")
async def ask_advisor(
    payload: AskRequest,
    _user: User = Depends(get_current_user),
) -> AdvisorResponseOut:
    """Answer a free-form portfolio question using current market context.

    The AI advisor is aware of:
    - Current macro regime and sentiment
    - All open positions and their P&L
    - SEBI risk limits and Indian market specifics

    Returns a structured response with the answer, recommended actions,
    and a risk level assessment.
    """
    advisor = _get_advisor()
    sentiment = await _get_current_sentiment()
    context = _make_mock_portfolio_context(regime=sentiment.regime, sentiment=sentiment)

    try:
        response = await advisor.ask(payload.question, context)
        return _advisor_to_out(response)
    except Exception as exc:
        _handle_api_error(exc)
        raise  # unreachable; satisfies type checker


@router.post(
    "/rebalance-suggest",
    response_model=AdvisorResponseOut,
    summary="Get AI-powered rebalancing suggestions",
)
async def suggest_rebalance(
    _user: User = Depends(get_current_user),
) -> AdvisorResponseOut:
    """Generate regime-aware rebalancing suggestions for the current portfolio.

    The AI considers:
    - Current macro regime (Crash/Bear/Neutral/Bull/Euphoria)
    - Sentiment score and FII/DII activity
    - Individual position weights vs. DRUVA's 10%/30% limits
    - SEBI T+1 settlement implications
    """
    advisor = _get_advisor()
    sentiment = await _get_current_sentiment()
    context = _make_mock_portfolio_context(regime=sentiment.regime, sentiment=sentiment)

    try:
        response = await advisor.suggest_rebalance(context)
        return _advisor_to_out(response)
    except Exception as exc:
        _handle_api_error(exc)
        raise  # unreachable; satisfies type checker


@router.post(
    "/evaluate-stock",
    response_model=AdvisorResponseOut,
    summary="Evaluate a stock for portfolio fit",
)
async def evaluate_stock(
    payload: EvaluateStockRequest,
    _user: User = Depends(get_current_user),
) -> AdvisorResponseOut:
    """Evaluate a stock for inclusion in the portfolio.

    Considers:
    - Fundamental metrics (P/E, ROCE, debt, EPS growth) if provided
    - Alignment with current macro regime
    - Sector concentration limits
    - Circuit-limit category of the stock
    """
    advisor = _get_advisor()
    sentiment = await _get_current_sentiment()
    context = _make_mock_portfolio_context(regime=sentiment.regime, sentiment=sentiment)

    try:
        response = await advisor.evaluate_stock(
            symbol=payload.symbol.upper(),
            fundamentals=payload.fundamentals,
            context=context,
        )
        return _advisor_to_out(response)
    except Exception as exc:
        _handle_api_error(exc)
        raise  # unreachable; satisfies type checker


@router.get(
    "/daily-briefing",
    response_model=DailyBriefingOut,
    summary="Get today's AI market briefing",
)
async def daily_briefing(
    _user: User = Depends(get_current_user),
) -> DailyBriefingOut:
    """Generate a concise daily market briefing (3-5 bullet points).

    Covers: market regime, sentiment, FII/DII activity, NIFTY trend,
    portfolio performance, and key watch items for the session.
    """
    advisor = _get_advisor()
    sentiment = await _get_current_sentiment()
    context = _make_mock_portfolio_context(regime=sentiment.regime, sentiment=sentiment)

    try:
        briefing_text = await advisor.daily_briefing(context)
        return DailyBriefingOut(
            briefing=briefing_text,
            regime=sentiment.regime,
            sentiment_score=sentiment.score,
            sentiment_label=sentiment.label,
        )
    except Exception as exc:
        _handle_api_error(exc)
        raise  # unreachable; satisfies type checker


@router.get(
    "/sentiment",
    response_model=SentimentOut,
    summary="Get current market sentiment reading",
)
async def get_sentiment(
    _user: User = Depends(get_current_user),
) -> SentimentOut:
    """Return the current composite market sentiment score.

    Aggregates India VIX, FII/DII net activity, Put-Call Ratio,
    NIFTY advance/decline ratio, and the HMM regime signal into a
    single composite score in [-100, +100].

    Results are cached for 15 minutes.
    """
    sentiment = await _get_current_sentiment()
    return _sentiment_to_out(sentiment)


@router.get(
    "/regime-status",
    response_model=RegimeStatusOut,
    summary="Get current regime and suggested allocation",
)
async def regime_status(
    _user: User = Depends(get_current_user),
) -> RegimeStatusOut:
    """Return the current market regime with suggested equity/cash allocation.

    The regime is determined by the HMM model; the suggested allocation is
    derived from DRUVA's regime-based capital deployment framework.

    Regimes and default equity allocations:
    - Crash:    20% equity, 80% cash/gold
    - Bear:     40% equity, 60% cash/gold
    - Neutral:  65% equity, 35% cash
    - Bull:     85% equity, 15% cash
    - Euphoria: 60% equity, 40% cash (trim winners at extremes)
    """
    sentiment = await _get_current_sentiment()
    regime = sentiment.regime
    equity_pct, cash_pct = _REGIME_ALLOCATION.get(regime, (65.0, 35.0))
    description = _REGIME_DESCRIPTIONS.get(regime, "Unknown regime.")

    return RegimeStatusOut(
        regime=regime,
        confidence=0.82,  # TODO: wire to live HMM confidence
        sentiment_score=sentiment.score,
        sentiment_label=sentiment.label,
        suggested_equity_pct=equity_pct,
        suggested_cash_pct=cash_pct,
        regime_description=description,
    )


# ---------------------------------------------------------------------------
# Error handling helper
# ---------------------------------------------------------------------------


def _handle_api_error(exc: Exception) -> None:
    """Translate Anthropic SDK and network errors to appropriate HTTP responses."""
    import anthropic as _anthropic

    error_msg = str(exc)
    logger.error("ai_advisor.api_error", error=error_msg, exc_info=True)

    if isinstance(exc, _anthropic.RateLimitError):
        raise HTTPException(
            status_code=429,
            detail="Claude API rate limit reached. Please retry after a moment.",
        ) from exc

    if isinstance(exc, (_anthropic.APIConnectionError, _anthropic.APITimeoutError)):
        raise HTTPException(
            status_code=503,
            detail="Claude API is temporarily unreachable. Please try again.",
        ) from exc

    if isinstance(exc, _anthropic.AuthenticationError):
        raise HTTPException(
            status_code=503,
            detail="AI advisor authentication failed. Check ANTHROPIC_API_KEY configuration.",
        ) from exc

    if isinstance(exc, _anthropic.APIError):
        raise HTTPException(
            status_code=502,
            detail=f"Claude API error: {error_msg}",
        ) from exc

    # Re-raise unexpected errors as 500
    raise HTTPException(
        status_code=500,
        detail=f"Unexpected error in AI advisor: {error_msg}",
    ) from exc
