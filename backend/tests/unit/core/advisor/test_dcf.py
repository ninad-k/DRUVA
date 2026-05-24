"""Unit tests for the three-stage DCF valuator + fundamentals provider abstraction."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.advisor.valuation import (
    FundamentalsView,
    LineItem,
    NullFundamentalsProvider,
    StaticFundamentalsProvider,
    build_provider,
    estimate_maintenance_capex,
    three_stage_dcf,
)


def _view(
    *,
    symbol: str = "TEST",
    net_income: list[float] | None = None,
    fcf: list[float] | None = None,
    capex: list[float] | None = None,
    dep: list[float] | None = None,
    market_cap: float | None = None,
    pe: float | None = None,
    shares: float | None = None,
) -> FundamentalsView:
    def to_items(values: list[float] | None) -> list[LineItem]:
        if not values:
            return []
        return [
            LineItem(period_end=date(2018 + i, 3, 31), value=v) for i, v in enumerate(values)
        ]

    return FundamentalsView(
        symbol=symbol,
        exchange="NSE",
        net_income=to_items(net_income),
        free_cash_flow=to_items(fcf),
        capital_expenditure=to_items(capex),
        depreciation=to_items(dep),
        market_cap=market_cap,
        pe_ratio=pe,
        shares_outstanding=shares,
    )


class TestEstimateMaintenanceCapex:
    def test_both_empty_returns_zero(self) -> None:
        assert estimate_maintenance_capex([], []) == 0.0

    def test_only_depreciation_returned(self) -> None:
        dep = [LineItem(period_end=date(2022, 3, 31), value=100)]
        assert estimate_maintenance_capex([], dep) == 100.0

    def test_min_of_capex_and_dep(self) -> None:
        dep = [LineItem(period_end=date(2022, 3, 31), value=200)]
        capex = [LineItem(period_end=date(2022, 3, 31), value=300)]
        # min(200, 300) = 200
        assert estimate_maintenance_capex(capex, dep) == 200.0
        # symmetric — capex lower wins.
        dep2 = [LineItem(period_end=date(2022, 3, 31), value=400)]
        capex2 = [LineItem(period_end=date(2022, 3, 31), value=150)]
        assert estimate_maintenance_capex(capex2, dep2) == 150.0


class TestThreeStageDCF:
    def test_full_history_produces_intrinsic_value(self) -> None:
        view = _view(
            net_income=[100, 110, 120, 132, 145],
            dep=[20, 22, 25, 27, 30],
            capex=[35, 38, 40, 42, 45],
            market_cap=1_000.0,
            shares=10.0,
        )
        result = three_stage_dcf(view)
        assert result is not None
        assert result.intrinsic_value_total > 0
        assert result.intrinsic_value_per_share is not None
        assert result.margin_of_safety_pct is not None
        assert not result.degraded
        # PVs should be ordered: terminal usually dominates over 10y horizon.
        assert result.terminal_pv > 0
        # Owner earnings = NI + Dep − maintenance_capex.
        # Maintenance capex = min(avg_dep_3y, avg_capex_3y) = min(27.33, 42.33) = 27.33
        # Latest NI = 145, latest dep = 30 → owner earnings = 145 + 30 − 27.33 ≈ 147.67
        assert result.owner_earnings == pytest.approx(147.67, abs=0.5)

    def test_fcf_fallback_when_no_net_income(self) -> None:
        view = _view(
            fcf=[80, 90, 100, 110, 121],
            market_cap=1_500.0,
            shares=15.0,
        )
        result = three_stage_dcf(view)
        assert result is not None
        assert result.owner_earnings == 121.0
        assert not result.degraded

    def test_pe_shortcut_marks_degraded(self) -> None:
        view = _view(market_cap=1_000.0, pe=20.0, shares=10.0)
        result = three_stage_dcf(view)
        assert result is not None
        assert result.degraded
        # Implied earnings = market_cap / pe = 50.
        assert result.owner_earnings == 50.0

    def test_returns_none_when_no_seed(self) -> None:
        view = _view(market_cap=1_000.0)  # no NI, no FCF, no PE.
        assert three_stage_dcf(view) is None

    def test_terminal_growth_capped_below_discount(self) -> None:
        view = _view(net_income=[100], market_cap=500.0)
        # Even if user asks for absurd terminal growth, it gets capped.
        result = three_stage_dcf(
            view,
            terminal_growth=0.50,
            discount_rate=0.10,
        )
        assert result is not None
        # Terminal growth must be < discount_rate − 0.01 = 0.09; and also <
        # growth_stage2 (default 0.04). So effective terminal growth = 0.04.
        assert result.inputs["terminal_growth"] <= result.inputs["discount_rate"] - 0.01

    def test_margin_of_safety_negative_when_overpriced(self) -> None:
        # Tiny intrinsic earnings, big market cap.
        view = _view(net_income=[10], market_cap=10_000.0, shares=100.0)
        result = three_stage_dcf(view)
        assert result is not None
        assert result.margin_of_safety_pct is not None
        assert result.margin_of_safety_pct < 0


class TestProviderFactory:
    @pytest.mark.asyncio
    async def test_null_provider_returns_none(self) -> None:
        provider = NullFundamentalsProvider()
        assert await provider.get("RELIANCE") is None

    @pytest.mark.asyncio
    async def test_static_provider_roundtrip(self) -> None:
        provider = StaticFundamentalsProvider()
        view = _view(symbol="HDFCBANK", net_income=[1, 2, 3], market_cap=100.0)
        provider.add(view)
        fetched = await provider.get("hdfcbank")
        assert fetched is not None
        assert fetched.symbol == "HDFCBANK"
        assert await provider.get("UNKNOWN") is None

    def test_build_provider_null_kind(self) -> None:
        provider = build_provider(kind="null")
        assert isinstance(provider, NullFundamentalsProvider)

    def test_build_provider_http_missing_base_url_returns_null(self) -> None:
        provider = build_provider(kind="http")
        # Without a base URL it must fall back rather than raise.
        assert isinstance(provider, NullFundamentalsProvider)

    def test_build_provider_repository_without_session_returns_null(self) -> None:
        provider = build_provider(kind="repository")
        assert isinstance(provider, NullFundamentalsProvider)
