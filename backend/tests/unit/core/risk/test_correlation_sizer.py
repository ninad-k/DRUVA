"""Unit tests for the correlation-multiplier position sizer."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.risk.correlation_sizer import (
    annualised_volatility_from_returns,
    average_correlation_with_book,
    compute_correlation_sizing,
    correlation_multiplier,
    volatility_adjusted_limit,
)


class TestVolatilityBuckets:
    @pytest.mark.parametrize(
        ("vol", "expected_cap"),
        [
            (0.10, 25.0),
            (0.15, 25.0),     # boundary inclusive
            (0.20, 17.5),
            (0.30, 17.5),
            (0.40, 10.0),
            (0.50, 10.0),
            (0.80, 5.0),
            (1.50, 5.0),       # fallback bucket
        ],
    )
    def test_buckets(self, vol: float, expected_cap: float) -> None:
        assert volatility_adjusted_limit(vol) == expected_cap

    def test_negative_vol_clipped_to_zero(self) -> None:
        assert volatility_adjusted_limit(-1.0) == 25.0


class TestCorrelationMultiplier:
    @pytest.mark.parametrize(
        ("rho", "expected"),
        [
            (0.95, 0.70),
            (0.80, 0.70),     # boundary inclusive
            (0.70, 0.85),
            (0.50, 1.00),
            (0.30, 1.05),
            (0.10, 1.10),
            (-0.20, 1.10),
        ],
    )
    def test_multiplier(self, rho: float, expected: float) -> None:
        assert correlation_multiplier(rho) == expected

    def test_nan_falls_back_to_one(self) -> None:
        assert correlation_multiplier(float("nan")) == 1.0


class TestComputeCorrelationSizing:
    def test_typical_low_vol_low_correlation(self) -> None:
        result = compute_correlation_sizing(
            annualised_volatility=0.12,
            avg_correlation=0.15,
            portfolio_value=1_000_000.0,
        )
        # Low vol bucket: 25% cap. Low correlation: 1.10x multiplier.
        assert result.base_cap_pct == 25.0
        assert result.correlation_multiplier == 1.10
        assert result.adjusted_cap_pct == pytest.approx(27.5)
        assert result.adjusted_cap_inr == pytest.approx(275_000.0)
        assert result.remaining_room_inr == pytest.approx(275_000.0)

    def test_high_vol_high_correlation_shrinks_cap(self) -> None:
        result = compute_correlation_sizing(
            annualised_volatility=0.55,
            avg_correlation=0.85,
            portfolio_value=2_000_000.0,
        )
        # >50% vol => 5% cap. ρ ≥ 0.80 => 0.70x multiplier.
        assert result.base_cap_pct == 5.0
        assert result.correlation_multiplier == 0.70
        assert result.adjusted_cap_pct == pytest.approx(3.5)
        assert result.adjusted_cap_inr == pytest.approx(70_000.0)

    def test_remaining_room_subtracts_current_position(self) -> None:
        result = compute_correlation_sizing(
            annualised_volatility=0.25,
            avg_correlation=0.50,
            portfolio_value=1_000_000.0,
            current_position_value=150_000.0,
        )
        # 0.30 bucket: 17.5%. Mid correlation: 1.0x. Cap = 175k. Room = 25k.
        assert result.adjusted_cap_pct == pytest.approx(17.5)
        assert result.remaining_room_inr == pytest.approx(25_000.0)

    def test_zero_portfolio_safe(self) -> None:
        result = compute_correlation_sizing(
            annualised_volatility=0.2,
            avg_correlation=0.3,
            portfolio_value=0.0,
        )
        assert result.adjusted_cap_inr == 0.0
        assert result.remaining_room_inr == 0.0

    def test_room_never_negative(self) -> None:
        result = compute_correlation_sizing(
            annualised_volatility=0.4,
            avg_correlation=0.9,
            portfolio_value=500_000.0,
            current_position_value=999_999.0,
        )
        assert result.remaining_room_inr == 0.0


class TestAnnualisedVolatility:
    def test_empty_returns(self) -> None:
        assert annualised_volatility_from_returns([]) == 0.0

    def test_constant_returns_zero_vol(self) -> None:
        assert annualised_volatility_from_returns([0.01, 0.01, 0.01]) == 0.0

    def test_known_input(self) -> None:
        rng = np.random.default_rng(42)
        returns = rng.normal(loc=0.0, scale=0.01, size=1000)
        ann = annualised_volatility_from_returns(returns)
        # σ ≈ 0.01 daily → annualised ≈ 0.01 * sqrt(252) ≈ 0.159
        assert 0.13 < ann < 0.18


class TestAverageCorrelation:
    def test_empty_book_returns_zero(self) -> None:
        cand = np.random.default_rng(0).normal(size=100)
        assert average_correlation_with_book(cand, []) == 0.0

    def test_perfect_self_correlation(self) -> None:
        cand = np.random.default_rng(1).normal(size=200)
        rho = average_correlation_with_book(cand, [cand])
        assert rho == pytest.approx(1.0, abs=1e-9)

    def test_independent_series_low_correlation(self) -> None:
        rng = np.random.default_rng(123)
        cand = rng.normal(size=500)
        book = [rng.normal(size=500) for _ in range(5)]
        rho = average_correlation_with_book(cand, book)
        assert abs(rho) < 0.15

    def test_short_series_skipped(self) -> None:
        cand = np.random.default_rng(0).normal(size=100)
        # All book series shorter than 30 observations → skipped → returns 0.
        book = [np.array([0.01] * 5) for _ in range(3)]
        assert average_correlation_with_book(cand, book) == 0.0
