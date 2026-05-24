"""Three-stage discounted-cash-flow intrinsic-value model.

Adapted from virattt/ai-hedge-fund (MIT). Mechanics:

  Stage 1 — high-growth phase (default 5 years, growth capped at 8%).
  Stage 2 — fade phase     (default 5 years, growth capped at 4%).
  Terminal — Gordon-growth perpetuity (default 2.5%).

A configurable margin-of-safety haircut is applied to the final intrinsic
value (Buffett-style conservatism; default 15%).

Owner earnings (Buffett's preferred FCF proxy) =
    net income + depreciation − maintenance capex

A separate ``estimate_maintenance_capex()`` helper distinguishes maintenance
vs. growth capex by assuming maintenance ≈ historical depreciation when no
explicit split is available — a reasonable rule-of-thumb for mature businesses
but coarse for asset-light tech firms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.advisor.valuation.fundamentals_provider import FundamentalsView, LineItem
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Defaults — calibrated for Indian large-cap equities. Override per call.
# ---------------------------------------------------------------------------

_DEFAULT_GROWTH_STAGE1 = 0.08
_DEFAULT_YEARS_STAGE1 = 5
_DEFAULT_GROWTH_STAGE2 = 0.04
_DEFAULT_YEARS_STAGE2 = 5
_DEFAULT_TERMINAL_GROWTH = 0.025
_DEFAULT_DISCOUNT_RATE = 0.10
_DEFAULT_MARGIN_OF_SAFETY = 0.15


@dataclass(frozen=True)
class DCFResult:
    intrinsic_value_total: float
    """Total equity intrinsic value in INR (or issuer currency)."""

    intrinsic_value_per_share: float | None
    """Per-share value if ``shares_outstanding`` is known."""

    margin_of_safety_pct: float | None
    """``(intrinsic - market) / market * 100`` — positive = undervalued."""

    owner_earnings: float
    """Latest-period owner earnings used as the DCF seed."""

    maintenance_capex: float
    """Maintenance capex estimate used in owner-earnings calculation."""

    stage1_pv: float
    stage2_pv: float
    terminal_pv: float

    inputs: dict[str, float]
    """Assumptions used (growth rates, discount, etc.) for transparency."""

    degraded: bool = False
    """``True`` if line-item history was missing and seed values were
    approximated from ratios alone."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def three_stage_dcf(
    view: FundamentalsView,
    *,
    growth_stage1: float = _DEFAULT_GROWTH_STAGE1,
    years_stage1: int = _DEFAULT_YEARS_STAGE1,
    growth_stage2: float = _DEFAULT_GROWTH_STAGE2,
    years_stage2: int = _DEFAULT_YEARS_STAGE2,
    terminal_growth: float = _DEFAULT_TERMINAL_GROWTH,
    discount_rate: float = _DEFAULT_DISCOUNT_RATE,
    margin_of_safety: float = _DEFAULT_MARGIN_OF_SAFETY,
) -> DCFResult | None:
    """Run a three-stage DCF on a ``FundamentalsView``.

    Returns ``None`` when there is not enough data to seed the model — i.e.
    no net-income / FCF history *and* no PE+EPS shortcut available.
    """
    # Caps mirroring Buffett's conservative bias.
    growth_stage1 = min(growth_stage1, 0.15)
    growth_stage2 = min(growth_stage2, growth_stage1)
    terminal_growth = min(terminal_growth, growth_stage2, discount_rate - 0.01)

    maintenance = estimate_maintenance_capex(
        view.capital_expenditure, view.depreciation
    )
    seed, degraded = _seed_owner_earnings(view, maintenance)
    if seed is None or seed <= 0:
        logger.info(
            "dcf.unable_to_seed",
            symbol=view.symbol,
            has_net_income=bool(view.net_income),
            has_fcf=bool(view.free_cash_flow),
            pe=view.pe_ratio,
        )
        return None

    # Stage 1 — explicit forecast at growth_stage1.
    stage1_pv = 0.0
    last_cash_flow = seed
    for year in range(1, years_stage1 + 1):
        last_cash_flow *= 1.0 + growth_stage1
        stage1_pv += last_cash_flow / ((1.0 + discount_rate) ** year)

    # Stage 2 — fade at growth_stage2.
    stage2_pv = 0.0
    for year in range(1, years_stage2 + 1):
        last_cash_flow *= 1.0 + growth_stage2
        stage2_pv += last_cash_flow / ((1.0 + discount_rate) ** (years_stage1 + year))

    # Terminal — Gordon perpetuity at terminal_growth.
    terminal_cf = last_cash_flow * (1.0 + terminal_growth)
    terminal_value = terminal_cf / (discount_rate - terminal_growth)
    terminal_pv = terminal_value / ((1.0 + discount_rate) ** (years_stage1 + years_stage2))

    intrinsic = (stage1_pv + stage2_pv + terminal_pv) * (1.0 - margin_of_safety)

    shares = _latest_shares(view)
    per_share = intrinsic / shares if shares and shares > 0 else None
    market_cap = view.market_cap
    mos_pct: float | None = None
    if market_cap and market_cap > 0:
        mos_pct = (intrinsic - market_cap) / market_cap * 100.0

    return DCFResult(
        intrinsic_value_total=round(intrinsic, 2),
        intrinsic_value_per_share=round(per_share, 4) if per_share is not None else None,
        margin_of_safety_pct=round(mos_pct, 2) if mos_pct is not None else None,
        owner_earnings=round(seed, 2),
        maintenance_capex=round(maintenance, 2),
        stage1_pv=round(stage1_pv, 2),
        stage2_pv=round(stage2_pv, 2),
        terminal_pv=round(terminal_pv, 2),
        inputs={
            "growth_stage1": growth_stage1,
            "years_stage1": float(years_stage1),
            "growth_stage2": growth_stage2,
            "years_stage2": float(years_stage2),
            "terminal_growth": terminal_growth,
            "discount_rate": discount_rate,
            "margin_of_safety": margin_of_safety,
        },
        degraded=degraded,
    )


def estimate_maintenance_capex(
    capex_history: Sequence[LineItem],
    depreciation_history: Sequence[LineItem],
) -> float:
    """Estimate maintenance capex (positive number) from history.

    Heuristic: maintenance capex ≈ trailing-3yr average depreciation, clamped
    above by trailing-3yr average reported capex (capex always ≥ maintenance,
    by definition). This deliberately under-estimates maintenance for high-
    growth firms with rising D&A — that conservatism flows through to a lower
    intrinsic value.
    """
    avg_dep = _abs_avg_tail(depreciation_history, n=3)
    avg_capex = _abs_avg_tail(capex_history, n=3)
    if avg_capex == 0.0 and avg_dep == 0.0:
        return 0.0
    if avg_capex == 0.0:
        return avg_dep
    if avg_dep == 0.0:
        return avg_capex
    return min(avg_dep, avg_capex)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _seed_owner_earnings(
    view: FundamentalsView, maintenance_capex: float
) -> tuple[float | None, bool]:
    """Pick the best available seed for the DCF.

    Priority:
      1. Owner earnings  = net_income + depreciation − maintenance_capex
      2. Free cash flow  (latest)
      3. Ratio shortcut  = market_cap / pe_ratio  (= net income proxy);
         flags ``degraded=True``.
    """
    if view.net_income:
        ni = view.net_income[-1].value
        dep = view.depreciation[-1].value if view.depreciation else 0.0
        return ni + dep - maintenance_capex, False
    if view.free_cash_flow:
        return view.free_cash_flow[-1].value, False
    if view.pe_ratio and view.market_cap and view.pe_ratio > 0:
        # Implied trailing earnings.
        return view.market_cap / view.pe_ratio, True
    return None, False


def _latest_shares(view: FundamentalsView) -> float | None:
    if view.shares_outstanding and view.shares_outstanding > 0:
        return view.shares_outstanding
    if view.shares_outstanding_history:
        return view.shares_outstanding_history[-1].value
    return None


def _abs_avg_tail(series: Sequence[LineItem], *, n: int) -> float:
    if not series:
        return 0.0
    tail = list(series[-n:])
    if not tail:
        return 0.0
    return sum(abs(li.value) for li in tail) / float(len(tail))
