"""Loss functions for Optuna hyperopt.

Optuna minimises by default; risk-adjusted return metrics are returned as
*negative* values so that "lower is better" lines up with "higher Sharpe".

All inputs are ``numpy.ndarray`` of *daily* portfolio returns expressed as
fractions (``0.012 == +1.2%``). Annualisation uses 252 trading days.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

LossFn = Callable[[np.ndarray], float]
"""Callable signature for any loss: ``ndarray of returns → float``."""

_TRADING_DAYS = 252


def sharpe_loss(returns: np.ndarray, risk_free: float = 0.07) -> float:
    """Negative annualised Sharpe ratio (risk-free in fractional units)."""
    if returns.size < 2:
        return 0.0
    excess = returns - (risk_free / _TRADING_DAYS)
    sigma = float(np.std(excess, ddof=1))
    if sigma == 0.0:
        return 0.0
    sharpe = float(np.mean(excess) / sigma * np.sqrt(_TRADING_DAYS))
    return -sharpe


def sortino_loss(returns: np.ndarray, risk_free: float = 0.07) -> float:
    """Negative annualised Sortino ratio — penalises downside volatility only."""
    if returns.size < 2:
        return 0.0
    excess = returns - (risk_free / _TRADING_DAYS)
    downside = excess[excess < 0.0]
    if downside.size < 2:
        return 0.0
    downside_dev = float(np.std(downside, ddof=1))
    if downside_dev == 0.0:
        return 0.0
    sortino = float(np.mean(excess) / downside_dev * np.sqrt(_TRADING_DAYS))
    return -sortino


def calmar_loss(returns: np.ndarray) -> float:
    """Negative Calmar — annualised return divided by max drawdown."""
    if returns.size < 2:
        return 0.0
    equity = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    max_dd = float(np.max(drawdown))
    if max_dd <= 0.0:
        return 0.0
    annual_return = float(equity[-1] ** (_TRADING_DAYS / returns.size) - 1.0)
    return -(annual_return / max_dd)


def cvar_loss(returns: np.ndarray, confidence: float = 0.95) -> float:
    """Positive CVaR (Expected Shortfall) — *minimising* tail-loss magnitude.

    Returns a *positive* number — ``+0.04 == 4%`` average loss in the worst
    ``1-confidence`` of days.
    """
    if returns.size < 2:
        return 0.0
    alpha = 1.0 - confidence
    threshold = float(np.quantile(returns, alpha))
    tail = returns[returns <= threshold]
    if tail.size == 0:
        return 0.0
    return float(-np.mean(tail))


def multi_objective_loss(
    returns: np.ndarray,
    *,
    weights: tuple[float, float, float] = (0.6, 0.3, 0.1),
) -> float:
    """Weighted Sharpe + Calmar + −CVaR. Default weights favour Sharpe.

    All three terms are oriented so "lower is better"; the result is a single
    scalar Optuna can minimise without multi-objective machinery.
    """
    w_sharpe, w_calmar, w_cvar = weights
    return (
        w_sharpe * sharpe_loss(returns)
        + w_calmar * calmar_loss(returns)
        + w_cvar * cvar_loss(returns)
    )
