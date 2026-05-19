"""REST endpoints for portfolio VaR / CVaR risk reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth.dependencies import get_current_user
from app.core.risk.var_engine import (
    PortfolioVaRReport,
    compute_historical_var,
    compute_portfolio_var_report,
    fetch_nifty_returns,
)
from app.db.models.user import User
from app.infrastructure.logging import get_logger
from pydantic import BaseModel

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class PositionInput(BaseModel):
    symbol: str
    weight_pct: float
    daily_returns: list[float]   # last 252 daily returns as fractions


class VaRRequest(BaseModel):
    positions: list[PositionInput]
    portfolio_value: float
    lookback_days: int = 252


class VaRResultOut(BaseModel):
    confidence_level: float
    var_pct: float
    cvar_pct: float
    var_inr: float
    cvar_inr: float
    n_observations: int


class PortfolioVaRReportOut(BaseModel):
    var_95: VaRResultOut
    var_99: VaRResultOut
    cvar_95: VaRResultOut
    cvar_99: VaRResultOut
    position_contributions: list[dict]
    computed_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _var_result_to_out(result) -> VaRResultOut:
    return VaRResultOut(
        confidence_level=result.confidence_level,
        var_pct=result.var_pct,
        cvar_pct=result.cvar_pct,
        var_inr=result.var_inr,
        cvar_inr=result.cvar_inr,
        n_observations=result.n_observations,
    )


def _report_to_out(report: PortfolioVaRReport) -> PortfolioVaRReportOut:
    contributions = [
        {
            "symbol": c.symbol,
            "weight_pct": c.weight_pct,
            "var_contribution_pct": c.var_contribution_pct,
            "standalone_var_pct": c.standalone_var_pct,
        }
        for c in report.position_contributions
    ]
    return PortfolioVaRReportOut(
        var_95=_var_result_to_out(report.var_95),
        var_99=_var_result_to_out(report.var_99),
        cvar_95=_var_result_to_out(report.cvar_95),
        cvar_99=_var_result_to_out(report.cvar_99),
        position_contributions=contributions,
        computed_at=report.computed_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/var", response_model=PortfolioVaRReportOut)
async def compute_var(
    payload: VaRRequest,
    _user: User = Depends(get_current_user),
) -> PortfolioVaRReportOut:
    """Compute historical VaR and CVaR for a portfolio.

    Accepts a list of positions with their recent daily returns and returns
    a full risk report including 95% and 99% VaR/CVaR and per-position
    contribution breakdown.
    """
    logger.info(
        "risk.var_request",
        n_positions=len(payload.positions),
        portfolio_value=payload.portfolio_value,
        lookback_days=payload.lookback_days,
    )

    positions = [
        {
            "symbol": p.symbol,
            "weight_pct": p.weight_pct,
            "daily_returns": p.daily_returns,
        }
        for p in payload.positions
    ]

    report = compute_portfolio_var_report(
        positions=positions,
        portfolio_value=payload.portfolio_value,
        lookback_days=payload.lookback_days,
    )

    return _report_to_out(report)


@router.get("/var/nifty-benchmark", response_model=dict)
async def nifty_benchmark(
    _user: User = Depends(get_current_user),
) -> dict:
    """Fetch NIFTY 50 VaR at 95% and 99% as a benchmark.

    Uses yfinance (via asyncio.to_thread) to pull historical data and
    returns VaR / CVaR metrics for the NIFTY 50 index.
    """
    logger.info("risk.nifty_benchmark_request")

    nifty_returns = await fetch_nifty_returns(lookback_days=252)

    # Use a nominal portfolio value of 100 for percentage-only display
    var_95 = compute_historical_var(nifty_returns, 0.95, 100.0)
    var_99 = compute_historical_var(nifty_returns, 0.99, 100.0)

    return {
        "index": "NIFTY 50",
        "var_95": _var_result_to_out(var_95).model_dump(),
        "var_99": _var_result_to_out(var_99).model_dump(),
    }
