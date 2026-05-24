"""Volatility-bucketed position cap with a correlation multiplier.

Adapted from virattt/ai-hedge-fund (MIT) risk-management agent. Complements —
not replaces — DRUVA's existing Kelly sizing and VaR engine:

  • Kelly tells us *how aggressive* a position can be given edge + odds.
  • VaR tells us *aggregate portfolio loss* under a tail scenario.
  • This sizer caps each new position by *its own* volatility and how
    correlated it is with the existing book.

Use the result as an *upper bound* alongside Kelly. The final size is the
``min(kelly, correlation_cap, sector_cap, single_position_limit)``.

Annualized vol assumes 252 trading days. Correlation is Pearson on daily
returns over the same lookback. Both inputs are expected to be pre-computed
upstream — this module is intentionally framework-agnostic and synchronous.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Bucket tables — defaults from virattt/ai-hedge-fund, lightly recalibrated
# for Indian large-caps where weekly 3-sigma moves of 5–8% are routine.
# ---------------------------------------------------------------------------

# (upper_inclusive_annualised_vol, cap_pct_of_portfolio)
_VOL_BUCKETS: tuple[tuple[float, float], ...] = (
    (0.15, 25.0),
    (0.30, 17.5),
    (0.50, 10.0),
    (1.00, 5.0),
)
_VOL_FALLBACK_CAP = 5.0  # >100% annualised vol — exotic / illiquid

# (lower_inclusive_avg_correlation, multiplier)
_CORR_BUCKETS: tuple[tuple[float, float], ...] = (
    (0.80, 0.70),
    (0.60, 0.85),
    (0.40, 1.00),
    (0.20, 1.05),
)
_CORR_FALLBACK_MULT = 1.10  # near-zero or negative correlation → small bonus


@dataclass(frozen=True)
class CorrelationSizing:
    """Result of a correlation-adjusted sizing computation."""

    annualised_volatility: float
    """Input vol, expressed as a fraction (e.g. 0.22 = 22% annualised)."""

    avg_correlation: float
    """Average Pearson correlation with existing book; in [-1, 1]."""

    base_cap_pct: float
    """Bucket cap from volatility alone, before correlation adjustment."""

    correlation_multiplier: float
    """Multiplier applied to ``base_cap_pct``."""

    adjusted_cap_pct: float
    """Final cap as a percentage of portfolio value, after multiplier."""

    adjusted_cap_inr: float
    """``adjusted_cap_pct`` translated into INR using ``portfolio_value``."""

    remaining_room_inr: float
    """``adjusted_cap_inr − current_position_inr``, floored at 0."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def volatility_adjusted_limit(annualised_vol: float) -> float:
    """Return the position cap (in % of portfolio) for an annualised vol level."""
    vol = max(0.0, float(annualised_vol))
    for upper, cap in _VOL_BUCKETS:
        if vol <= upper:
            return cap
    return _VOL_FALLBACK_CAP


def correlation_multiplier(avg_correlation: float) -> float:
    """Return the multiplier applied to the vol-bucket cap for a given mean ρ.

    Higher correlation → shrink the cap; lower correlation → small bonus.
    Negative correlations (rare in equity books) get the maximum bonus.
    """
    rho = float(avg_correlation)
    if np.isnan(rho):
        return 1.0
    for lower, mult in _CORR_BUCKETS:
        if rho >= lower:
            return mult
    return _CORR_FALLBACK_MULT


def compute_correlation_sizing(
    *,
    annualised_volatility: float,
    avg_correlation: float,
    portfolio_value: float,
    current_position_value: float = 0.0,
) -> CorrelationSizing:
    """Compute a vol- and correlation-adjusted cap for a single name.

    Args:
        annualised_volatility: σ * √252 of the candidate's daily returns,
            expressed as a fraction (0.22 = 22%).
        avg_correlation: mean Pearson ρ of the candidate's daily returns
            against each existing position's daily returns.
        portfolio_value: total portfolio value in INR.
        current_position_value: current exposure to this symbol in INR (0 for
            a new position).
    """
    if portfolio_value <= 0:
        logger.warning("correlation_sizer.zero_portfolio")
        return CorrelationSizing(
            annualised_volatility=annualised_volatility,
            avg_correlation=avg_correlation,
            base_cap_pct=0.0,
            correlation_multiplier=1.0,
            adjusted_cap_pct=0.0,
            adjusted_cap_inr=0.0,
            remaining_room_inr=0.0,
        )

    base_cap = volatility_adjusted_limit(annualised_volatility)
    mult = correlation_multiplier(avg_correlation)
    adjusted_pct = base_cap * mult
    adjusted_inr = adjusted_pct / 100.0 * portfolio_value
    remaining = max(adjusted_inr - max(0.0, current_position_value), 0.0)

    return CorrelationSizing(
        annualised_volatility=round(float(annualised_volatility), 6),
        avg_correlation=round(float(avg_correlation), 6),
        base_cap_pct=round(base_cap, 4),
        correlation_multiplier=round(mult, 4),
        adjusted_cap_pct=round(adjusted_pct, 4),
        adjusted_cap_inr=round(adjusted_inr, 2),
        remaining_room_inr=round(remaining, 2),
    )


def annualised_volatility_from_returns(daily_returns: np.ndarray | list[float]) -> float:
    """Compute σ * √252 from a daily-return series. Returns 0 on empty input."""
    arr = np.asarray(daily_returns, dtype=float)
    if arr.size < 2:
        return 0.0
    return float(np.std(arr, ddof=1) * np.sqrt(252.0))


def average_correlation_with_book(
    candidate_returns: np.ndarray | list[float],
    book_returns: list[np.ndarray | list[float]],
) -> float:
    """Mean Pearson ρ of ``candidate_returns`` vs each series in ``book_returns``.

    Returns 0.0 when the book is empty (i.e. first position) or when any
    series is too short for a stable correlation (< 30 observations).
    """
    if not book_returns:
        return 0.0
    cand = np.asarray(candidate_returns, dtype=float)
    rhos: list[float] = []
    for other in book_returns:
        arr = np.asarray(other, dtype=float)
        n = min(cand.size, arr.size)
        if n < 30:
            continue
        x = cand[-n:]
        y = arr[-n:]
        if float(np.std(x)) == 0.0 or float(np.std(y)) == 0.0:
            continue
        rho = float(np.corrcoef(x, y)[0, 1])
        if np.isnan(rho):
            continue
        rhos.append(rho)
    if not rhos:
        return 0.0
    return float(np.mean(rhos))
