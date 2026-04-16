"""Black–Scholes pricing & Greeks (vectorized).

Pure numpy/scipy — no broker calls, no DB. Inputs as floats; the caller
should format using ``Decimal`` outside this module.

Conventions:
- ``S``  spot price
- ``K``  strike
- ``T``  time to expiry in years (e.g. 7 / 365)
- ``r``  risk-free rate, decimal (e.g. 0.07 for 7 %)
- ``q``  continuous dividend yield (default 0)
- ``sigma`` volatility, decimal (e.g. 0.18 for 18 %)
- ``option_type`` in {"CE", "PE"} (Indian convention) or {"call","put"}
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm


def _is_call(option_type: str) -> bool:
    return option_type.upper() in {"CE", "C", "CALL"}


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    theta: float  # per day
    vega: float   # per 1 % vol move
    rho: float    # per 1 % rate move


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        return float("nan"), float("nan")
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    q: float = 0.0,
) -> float:
    """Black–Scholes price (with continuous dividend yield)."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(0.0, S - K) if _is_call(option_type) else max(0.0, K - S)
        return intrinsic
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    if _is_call(option_type):
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    q: float = 0.0,
) -> Greeks:
    """Return price plus the standard greeks. Theta is per-day; vega/rho are
    per-1 % move (i.e. divided by 100) so the numbers read naturally."""
    p = price(S, K, T, r, sigma, option_type, q)
    if T <= 0 or sigma <= 0:
        return Greeks(price=p, delta=0.0, gamma=0.0, theta=0.0, vega=0.0, rho=0.0)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    is_call = _is_call(option_type)
    sqrt_T = math.sqrt(T)
    pdf_d1 = norm.pdf(d1)
    delta = (math.exp(-q * T) * norm.cdf(d1)) if is_call else (math.exp(-q * T) * (norm.cdf(d1) - 1))
    gamma = math.exp(-q * T) * pdf_d1 / (S * sigma * sqrt_T)
    if is_call:
        theta = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * sqrt_T)
            - r * K * math.exp(-r * T) * norm.cdf(d2)
            + q * S * math.exp(-q * T) * norm.cdf(d1)
        )
        rho = K * T * math.exp(-r * T) * norm.cdf(d2) / 100.0
    else:
        theta = (
            -S * math.exp(-q * T) * pdf_d1 * sigma / (2 * sqrt_T)
            + r * K * math.exp(-r * T) * norm.cdf(-d2)
            - q * S * math.exp(-q * T) * norm.cdf(-d1)
        )
        rho = -K * T * math.exp(-r * T) * norm.cdf(-d2) / 100.0
    vega = S * math.exp(-q * T) * pdf_d1 * sqrt_T / 100.0
    return Greeks(
        price=p,
        delta=delta,
        gamma=gamma,
        theta=theta / 365.0,  # per calendar day
        vega=vega,
        rho=rho,
    )


def implied_vol(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str,
    q: float = 0.0,
    *,
    tol: float = 1e-5,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson on Black-Scholes price. Falls back to bisection if
    Newton diverges (small vega regions)."""
    if market_price <= 0 or T <= 0:
        return float("nan")

    sigma = 0.2  # initial guess
    for _ in range(max_iter):
        try:
            theo = price(S, K, T, r, sigma, option_type, q)
            d1, _ = _d1_d2(S, K, T, r, q, sigma)
            vega_per_1 = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
            if vega_per_1 < 1e-8:
                break
            diff = theo - market_price
            if abs(diff) < tol:
                return sigma
            sigma -= diff / vega_per_1
            if sigma <= 0:
                sigma = 1e-4
        except Exception:  # noqa: BLE001
            break

    # Bisection fallback
    lo, hi = 1e-4, 5.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if price(S, K, T, r, mid, option_type, q) > market_price:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            return mid
    return float("nan")


def vectorized_greeks(
    S: float,
    strikes: np.ndarray,
    T: float,
    r: float,
    sigmas: np.ndarray,
    option_type: str,
    q: float = 0.0,
) -> dict[str, np.ndarray]:
    """Greeks across an array of strikes/IVs at once. Used for a full chain."""
    sigmas = np.where(sigmas <= 0, 1e-4, sigmas)
    sqrt_T = math.sqrt(T) if T > 0 else 1e-9
    d1 = (np.log(S / strikes) + (r - q + 0.5 * sigmas ** 2) * T) / (sigmas * sqrt_T)
    d2 = d1 - sigmas * sqrt_T
    pdf_d1 = norm.pdf(d1)
    is_call = _is_call(option_type)
    delta = np.exp(-q * T) * (norm.cdf(d1) if is_call else norm.cdf(d1) - 1)
    gamma = np.exp(-q * T) * pdf_d1 / (S * sigmas * sqrt_T)
    vega = S * np.exp(-q * T) * pdf_d1 * sqrt_T / 100.0
    if is_call:
        theta = (
            -S * np.exp(-q * T) * pdf_d1 * sigmas / (2 * sqrt_T)
            - r * strikes * np.exp(-r * T) * norm.cdf(d2)
            + q * S * np.exp(-q * T) * norm.cdf(d1)
        )
    else:
        theta = (
            -S * np.exp(-q * T) * pdf_d1 * sigmas / (2 * sqrt_T)
            + r * strikes * np.exp(-r * T) * norm.cdf(-d2)
            - q * S * np.exp(-q * T) * norm.cdf(-d1)
        )
    return {
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta / 365.0,
    }
