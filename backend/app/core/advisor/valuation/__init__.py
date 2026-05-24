"""Equity valuation primitives (DCF, intrinsic value, fundamentals view).

Adapted from virattt/ai-hedge-fund (MIT) for Indian equity markets.
"""

from app.core.advisor.valuation.dcf import (
    DCFResult,
    estimate_maintenance_capex,
    three_stage_dcf,
)
from app.core.advisor.valuation.fundamentals_provider import (
    FundamentalsProvider,
    FundamentalsView,
    LineItem,
    NullFundamentalsProvider,
    RepositoryFundamentalsProvider,
    StaticFundamentalsProvider,
    build_provider,
    get_fundamentals_provider,
)

__all__ = [
    "DCFResult",
    "estimate_maintenance_capex",
    "three_stage_dcf",
    "FundamentalsProvider",
    "FundamentalsView",
    "LineItem",
    "NullFundamentalsProvider",
    "RepositoryFundamentalsProvider",
    "StaticFundamentalsProvider",
    "build_provider",
    "get_fundamentals_provider",
]
