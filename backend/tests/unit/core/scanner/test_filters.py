"""Unit tests for the universe filter chain — Phase F3."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.scanner.filters import (
    AgeFilter,
    FilterPipeline,
    FilterResult,
    InstrumentSnapshot,
    PrecisionFilter,
    PriceFilter,
    RangeStabilityFilter,
    VolumeFilter,
    build_pipeline_from_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def snap(
    symbol: str = "RELIANCE",
    close: float = 2500.0,
    avg_daily_turnover_inr: float = 50_00_00_000.0,
    atr_pct: float = 1.5,
    listing_date: date | None = date(2000, 1, 1),
    tick_size: float = 0.05,
    lot_size: int = 1,
) -> InstrumentSnapshot:
    return InstrumentSnapshot(
        symbol=symbol,
        exchange="NSE",
        close=close,
        avg_daily_turnover_inr=avg_daily_turnover_inr,
        atr_pct=atr_pct,
        listing_date=listing_date,
        tick_size=tick_size,
        lot_size=lot_size,
    )


# ---------------------------------------------------------------------------
# FilterResult
# ---------------------------------------------------------------------------

class TestFilterResult:
    def test_ok(self):
        r = FilterResult.ok("INFY", "volume_filter")
        assert r.passed
        assert r.symbol == "INFY"

    def test_reject(self):
        r = FilterResult.reject("INFY", "volume_filter", reason="too thin")
        assert not r.passed
        assert r.reason == "too thin"


# ---------------------------------------------------------------------------
# VolumeFilter
# ---------------------------------------------------------------------------

class TestVolumeFilter:
    def test_passes_above_threshold(self):
        f = VolumeFilter(min_turnover_inr=1_00_00_000)
        assert f.apply(snap(avg_daily_turnover_inr=2_00_00_000)).passed

    def test_rejects_below_threshold(self):
        f = VolumeFilter(min_turnover_inr=5_00_00_000)
        r = f.apply(snap(avg_daily_turnover_inr=1_00_00_000))
        assert not r.passed
        assert "turnover" in r.reason

    def test_passes_at_exact_threshold(self):
        f = VolumeFilter(min_turnover_inr=5_00_00_000)
        assert f.apply(snap(avg_daily_turnover_inr=5_00_00_000)).passed


# ---------------------------------------------------------------------------
# PriceFilter
# ---------------------------------------------------------------------------

class TestPriceFilter:
    def test_passes_within_band(self):
        f = PriceFilter(min_price=10, max_price=10_000)
        assert f.apply(snap(close=500)).passed

    def test_rejects_too_cheap(self):
        f = PriceFilter(min_price=10)
        r = f.apply(snap(close=5))
        assert not r.passed
        assert "min" in r.reason

    def test_rejects_too_expensive(self):
        f = PriceFilter(max_price=500)
        r = f.apply(snap(close=1000))
        assert not r.passed
        assert "max" in r.reason

    def test_passes_at_min_boundary(self):
        f = PriceFilter(min_price=100, max_price=5000)
        assert f.apply(snap(close=100)).passed

    def test_passes_at_max_boundary(self):
        f = PriceFilter(min_price=10, max_price=5000)
        assert f.apply(snap(close=5000)).passed


# ---------------------------------------------------------------------------
# RangeStabilityFilter
# ---------------------------------------------------------------------------

class TestRangeStabilityFilter:
    def test_passes_in_range(self):
        f = RangeStabilityFilter(min_atr_pct=0.5, max_atr_pct=8.0)
        assert f.apply(snap(atr_pct=2.0)).passed

    def test_rejects_too_flat(self):
        f = RangeStabilityFilter(min_atr_pct=0.5)
        r = f.apply(snap(atr_pct=0.1))
        assert not r.passed
        assert "min" in r.reason.lower() or "flat" in r.reason.lower() or "illiquid" in r.reason

    def test_rejects_too_volatile(self):
        f = RangeStabilityFilter(max_atr_pct=8.0)
        r = f.apply(snap(atr_pct=15.0))
        assert not r.passed
        assert "erratic" in r.reason or "max" in r.reason.lower()

    def test_passes_at_boundaries(self):
        f = RangeStabilityFilter(min_atr_pct=0.5, max_atr_pct=8.0)
        assert f.apply(snap(atr_pct=0.5)).passed
        assert f.apply(snap(atr_pct=8.0)).passed


# ---------------------------------------------------------------------------
# AgeFilter
# ---------------------------------------------------------------------------

class TestAgeFilter:
    def test_passes_old_instrument(self):
        f = AgeFilter(min_listing_days=365)
        old_date = date.today() - timedelta(days=730)
        assert f.apply(snap(listing_date=old_date)).passed

    def test_rejects_fresh_ipo(self):
        f = AgeFilter(min_listing_days=365)
        fresh = date.today() - timedelta(days=30)
        r = f.apply(snap(listing_date=fresh))
        assert not r.passed
        assert "days ago" in r.reason

    def test_passes_when_no_listing_date(self):
        f = AgeFilter(min_listing_days=365)
        assert f.apply(snap(listing_date=None)).passed

    def test_exact_boundary_passes(self):
        f = AgeFilter(min_listing_days=365)
        exactly = date.today() - timedelta(days=365)
        assert f.apply(snap(listing_date=exactly)).passed


# ---------------------------------------------------------------------------
# PrecisionFilter
# ---------------------------------------------------------------------------

class TestPrecisionFilter:
    def test_passes_standard_equity(self):
        f = PrecisionFilter(max_tick_size=1.0, max_lot_size=1)
        assert f.apply(snap(tick_size=0.05, lot_size=1)).passed

    def test_rejects_large_tick(self):
        f = PrecisionFilter(max_tick_size=0.5)
        r = f.apply(snap(tick_size=1.0))
        assert not r.passed
        assert "tick" in r.reason

    def test_rejects_large_lot(self):
        f = PrecisionFilter(max_lot_size=1)
        r = f.apply(snap(lot_size=25))
        assert not r.passed
        assert "lot" in r.reason

    def test_passes_fo_name_with_relaxed_lot(self):
        f = PrecisionFilter(max_tick_size=1.0, max_lot_size=500)
        assert f.apply(snap(tick_size=0.05, lot_size=250)).passed


# ---------------------------------------------------------------------------
# FilterPipeline
# ---------------------------------------------------------------------------

class TestFilterPipeline:
    def test_all_pass(self):
        pipeline = FilterPipeline([VolumeFilter(min_turnover_inr=1_00_000), PriceFilter()])
        result = pipeline.run([snap()])
        assert snap().symbol in result.passed
        assert result.n_passed == 1
        assert result.n_rejected == 0

    def test_one_rejected(self):
        pipeline = FilterPipeline([VolumeFilter(min_turnover_inr=999_99_99_999)])
        result = pipeline.run([snap()])
        assert result.n_rejected == 1
        assert result.n_passed == 0

    def test_short_circuits_on_first_rejection(self):
        # VolumeFilter rejects; PriceFilter should never run
        calls: list[str] = []

        class SpyPriceFilter(PriceFilter):
            def apply(self, s):
                calls.append("price")
                return super().apply(s)

        pipeline = FilterPipeline([VolumeFilter(min_turnover_inr=999_99_99_999), SpyPriceFilter()])
        pipeline.run([snap()])
        assert calls == []  # price filter never called

    def test_multiple_instruments(self):
        pipeline = FilterPipeline([PriceFilter(min_price=100, max_price=3000)])
        snaps = [
            snap(symbol="A", close=200),
            snap(symbol="B", close=50),    # rejected — below min
            snap(symbol="C", close=5000),  # rejected — above max
        ]
        result = pipeline.run(snaps)
        assert "A" in result.passed
        assert "B" in result.rejected
        assert "C" in result.rejected

    def test_rejection_breakdown(self):
        pipeline = FilterPipeline([VolumeFilter(min_turnover_inr=999_99_99_999)])
        snaps = [snap(symbol="A"), snap(symbol="B")]
        result = pipeline.run(snaps)
        breakdown = result.rejection_breakdown()
        assert breakdown.get("volume_filter", 0) == 2

    def test_empty_universe(self):
        pipeline = FilterPipeline([VolumeFilter()])
        result = pipeline.run([])
        assert result.n_passed == 0
        assert result.n_rejected == 0


# ---------------------------------------------------------------------------
# build_pipeline_from_config
# ---------------------------------------------------------------------------

class TestBuildPipelineFromConfig:
    def test_default_has_five_filters(self):
        p = build_pipeline_from_config()
        assert len(p._filters) == 5

    def test_flat_dict_custom(self):
        p = build_pipeline_from_config({"volume": {"min_turnover_inr": 1_00_00_000}})
        vf = next(f for f in p._filters if isinstance(f, VolumeFilter))
        assert vf.min_turnover_inr == 1_00_00_000

    def test_flat_dict_disable(self):
        p = build_pipeline_from_config({"precision": False, "age": False})
        assert not any(isinstance(f, PrecisionFilter) for f in p._filters)
        assert not any(isinstance(f, AgeFilter) for f in p._filters)
        assert len(p._filters) == 3

    def test_list_style(self):
        cfg = [
            {"name": "volume_filter", "min_turnover_inr": 2_00_00_000},
            {"name": "price_filter", "min_price": 50},
        ]
        p = build_pipeline_from_config(cfg)
        assert len(p._filters) == 2

    def test_unknown_filter_raises(self):
        with pytest.raises(ValueError, match="Unknown filter"):
            build_pipeline_from_config([{"name": "nonexistent_filter"}])
