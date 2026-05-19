"""Historical Value at Risk (VaR) and Conditional VaR (CVaR / Expected Shortfall).

Methodology: Historical simulation — no parametric assumptions.
  VaR(α): the loss not exceeded with probability α over a 1-day horizon.
  CVaR(α): mean of losses beyond VaR(α) — also called Expected Shortfall (ES).

All calculations use daily log-returns over a 252-day rolling window.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class VaRResult:
    confidence_level: float        # e.g. 0.95
    var_pct: float                 # e.g. 2.34 (means 2.34% of portfolio)
    cvar_pct: float                # always >= var_pct
    var_inr: float                 # var_pct * portfolio_value / 100
    cvar_inr: float
    n_observations: int            # days of history used


@dataclass(frozen=True)
class PositionVaRContribution:
    symbol: str
    weight_pct: float              # position weight in portfolio
    var_contribution_pct: float    # this position's share of portfolio VaR (%)
    standalone_var_pct: float      # VaR if this were 100% of portfolio


@dataclass(frozen=True)
class PortfolioVaRReport:
    var_95: VaRResult
    var_99: VaRResult
    cvar_95: VaRResult
    cvar_99: VaRResult
    position_contributions: list[PositionVaRContribution]
    computed_at: str               # ISO UTC timestamp


def compute_historical_var(
    returns: np.ndarray,
    confidence_level: float,
    portfolio_value: float,
) -> VaRResult:
    """Compute historical VaR and CVaR for a return series.

    Args:
        returns: 1-D array of daily returns as fractions (e.g. 0.012 = +1.2%)
        confidence_level: e.g. 0.95 for 95% VaR
        portfolio_value: current portfolio value in INR
    """
    if len(returns) == 0:
        logger.warning("var_engine.empty_returns", confidence_level=confidence_level)
        return VaRResult(
            confidence_level=confidence_level,
            var_pct=0.0,
            cvar_pct=0.0,
            var_inr=0.0,
            cvar_inr=0.0,
            n_observations=0,
        )

    sorted_returns = np.sort(returns)  # ascending: worst losses at the front
    alpha = 1.0 - confidence_level

    # VaR threshold index: the (1-alpha) percentile of losses
    # np.percentile at alpha*100 of sorted returns gives the loss threshold
    var_threshold = np.percentile(sorted_returns, alpha * 100.0)

    # VaR is expressed as a positive loss percentage
    var_pct = float(-var_threshold * 100.0)

    # CVaR: mean of returns worse than (or equal to) the VaR threshold
    tail_returns = sorted_returns[sorted_returns <= var_threshold]
    if len(tail_returns) == 0:
        cvar_pct = var_pct
    else:
        cvar_pct = float(-np.mean(tail_returns) * 100.0)

    # Ensure CVaR >= VaR (can differ slightly due to discrete history)
    cvar_pct = max(cvar_pct, var_pct)

    var_inr = var_pct * portfolio_value / 100.0
    cvar_inr = cvar_pct * portfolio_value / 100.0

    logger.debug(
        "var_engine.computed",
        confidence_level=confidence_level,
        var_pct=round(var_pct, 4),
        cvar_pct=round(cvar_pct, 4),
        n_observations=len(returns),
    )

    return VaRResult(
        confidence_level=confidence_level,
        var_pct=round(var_pct, 4),
        cvar_pct=round(cvar_pct, 4),
        var_inr=round(var_inr, 2),
        cvar_inr=round(cvar_inr, 2),
        n_observations=len(returns),
    )


def compute_portfolio_var_report(
    positions: list[dict],
    portfolio_value: float,
    lookback_days: int = 252,
) -> PortfolioVaRReport:
    """Compute a full VaR report for a portfolio.

    Args:
        positions: list of dicts with keys:
            - symbol: str
            - weight_pct: float  (e.g. 30.0 for 30% weight)
            - daily_returns: list[float]  (last N days, as fractions)
        portfolio_value: current portfolio value in INR
        lookback_days: number of historical days to use (default 252 = 1 year)
    """
    logger.info(
        "var_engine.portfolio_report_start",
        n_positions=len(positions),
        portfolio_value=portfolio_value,
        lookback_days=lookback_days,
    )

    if not positions:
        empty_var = VaRResult(
            confidence_level=0.95,
            var_pct=0.0,
            cvar_pct=0.0,
            var_inr=0.0,
            cvar_inr=0.0,
            n_observations=0,
        )
        empty_var_99 = VaRResult(
            confidence_level=0.99,
            var_pct=0.0,
            cvar_pct=0.0,
            var_inr=0.0,
            cvar_inr=0.0,
            n_observations=0,
        )
        return PortfolioVaRReport(
            var_95=empty_var,
            var_99=empty_var_99,
            cvar_95=empty_var,
            cvar_99=empty_var_99,
            position_contributions=[],
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    # Determine the minimum return series length across positions
    min_len = min(len(p["daily_returns"]) for p in positions)
    effective_len = min(min_len, lookback_days)

    if effective_len == 0:
        logger.warning("var_engine.no_return_data")
        empty_var = VaRResult(
            confidence_level=0.95,
            var_pct=0.0,
            cvar_pct=0.0,
            var_inr=0.0,
            cvar_inr=0.0,
            n_observations=0,
        )
        empty_var_99 = VaRResult(
            confidence_level=0.99,
            var_pct=0.0,
            cvar_pct=0.0,
            var_inr=0.0,
            cvar_inr=0.0,
            n_observations=0,
        )
        return PortfolioVaRReport(
            var_95=empty_var,
            var_99=empty_var_99,
            cvar_95=empty_var,
            cvar_99=empty_var_99,
            position_contributions=[],
            computed_at=datetime.now(timezone.utc).isoformat(),
        )

    # Build portfolio return series as weighted sum of position returns
    portfolio_returns = np.zeros(effective_len)
    for pos in positions:
        weight = pos["weight_pct"] / 100.0
        pos_returns = np.array(pos["daily_returns"][-effective_len:], dtype=float)
        portfolio_returns += weight * pos_returns

    # Compute portfolio-level VaR / CVaR at 95% and 99%
    var_95 = compute_historical_var(portfolio_returns, 0.95, portfolio_value)
    var_99 = compute_historical_var(portfolio_returns, 0.99, portfolio_value)
    cvar_95 = var_95   # var_95 already has cvar_pct populated; reuse struct for cvar_95 slot
    cvar_99 = var_99

    # Per-position standalone VaR and contribution
    contributions: list[PositionVaRContribution] = []
    portfolio_var_95_pct = var_95.var_pct if var_95.var_pct != 0 else 1.0  # avoid div-by-zero

    for pos in positions:
        symbol = pos["symbol"]
        weight_pct = pos["weight_pct"]
        weight = weight_pct / 100.0

        pos_returns = np.array(pos["daily_returns"][-effective_len:], dtype=float)
        # Standalone VaR: if this position were 100% of the portfolio
        standalone = compute_historical_var(pos_returns, 0.95, portfolio_value)
        standalone_var_pct = standalone.var_pct

        # Contribution approximation: weight * standalone_var / portfolio_var * portfolio_var
        # Simplified: contribution_pct = (weight * standalone_var_pct) / portfolio_var_95_pct * 100
        raw_contribution = weight * standalone_var_pct
        var_contribution_pct = round(
            (raw_contribution / portfolio_var_95_pct) * 100.0, 4
        )

        contributions.append(
            PositionVaRContribution(
                symbol=symbol,
                weight_pct=round(weight_pct, 4),
                var_contribution_pct=var_contribution_pct,
                standalone_var_pct=round(standalone_var_pct, 4),
            )
        )

    # Sort by contribution descending
    contributions.sort(key=lambda c: c.var_contribution_pct, reverse=True)

    computed_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "var_engine.portfolio_report_done",
        var_95_pct=var_95.var_pct,
        var_99_pct=var_99.var_pct,
        computed_at=computed_at,
    )

    return PortfolioVaRReport(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        position_contributions=contributions,
        computed_at=computed_at,
    )


async def fetch_nifty_returns(lookback_days: int = 252) -> np.ndarray:
    """Fetch NIFTY 50 daily log-returns for the past *lookback_days* trading days.

    Uses yfinance in a thread pool so the async event loop is not blocked.

    Returns:
        1-D numpy array of daily returns as fractions (log-returns).
        Returns an empty array if the fetch fails.
    """

    def _fetch() -> np.ndarray:
        try:
            import yfinance as yf  # optional dep — only imported at call time

            ticker = yf.Ticker("^NSEI")
            # Fetch slightly more than needed to account for weekends / holidays
            hist = ticker.history(period=f"{lookback_days + 60}d", interval="1d")
            if hist.empty:
                logger.warning("var_engine.nifty_no_data")
                return np.array([], dtype=float)

            closes = hist["Close"].dropna().values
            if len(closes) < 2:
                return np.array([], dtype=float)

            # Log-returns: ln(P_t / P_{t-1})
            log_returns = np.diff(np.log(closes))
            # Return the last lookback_days observations
            return log_returns[-lookback_days:]
        except Exception as exc:  # noqa: BLE001
            logger.error("var_engine.nifty_fetch_error", error=str(exc))
            return np.array([], dtype=float)

    return await asyncio.to_thread(_fetch)
