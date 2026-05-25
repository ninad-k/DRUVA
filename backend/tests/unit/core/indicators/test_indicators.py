"""Unit tests for the unified indicator library — Phase K."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.core.indicators import registry
from app.core.indicators.base import IndicatorResult
from app.core.indicators.numpy_impl import (
    atr,
    bollinger_bands,
    cci,
    donchian_channels,
    ema,
    macd,
    obv,
    roc,
    rsi,
    sma,
    stochastic,
    supertrend,
    williams_r,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prices(n: int = 100, start: float = 100.0, step: float = 1.0) -> np.ndarray:
    """Linearly increasing close prices — predictable for assertions."""
    return np.linspace(start, start + step * (n - 1), n)


def _random_ohlcv(n: int = 100, seed: int = 42):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0, 2, n)
    low = close - rng.uniform(0, 2, n)
    volume = rng.uniform(1e6, 1e7, n)
    return high, low, close, volume


HIGH, LOW, CLOSE, VOLUME = _random_ohlcv(200)
LIN = _prices(200)


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

class TestSma:
    def test_returns_indicator_result(self):
        r = sma(LIN, length=10)
        assert isinstance(r, IndicatorResult)

    def test_correct_length(self):
        r = sma(LIN, length=10)
        assert len(r.value) == len(LIN)

    def test_nan_prefix(self):
        r = sma(LIN, length=10)
        assert np.all(np.isnan(r.value[:9]))

    def test_known_value_linear_series(self):
        # SMA(10) on [1..10] = 5.5
        closes = list(range(1, 21))
        r = sma(closes, length=10)
        assert abs(r.value[9] - 5.5) < 1e-9

    def test_single_element(self):
        r = sma([42.0], length=1)
        assert r.value[0] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestEma:
    def test_returns_indicator_result(self):
        r = ema(LIN, length=20)
        assert isinstance(r, IndicatorResult)

    def test_nan_prefix(self):
        r = ema(LIN, length=20)
        assert np.all(np.isnan(r.value[:19]))

    def test_ema_lags_behind_rising_prices(self):
        # EMA of rising prices should lag below the last close
        r = ema(LIN, length=20)
        assert r.value[-1] < LIN[-1]

    def test_meta_name(self):
        r = ema(LIN, length=10)
        assert r.meta.name == "ema"


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class TestRsi:
    def test_value_range(self):
        r = rsi(CLOSE, length=14)
        valid = r.value[~np.isnan(r.value)]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)

    def test_nan_prefix(self):
        r = rsi(CLOSE, length=14)
        assert np.all(np.isnan(r.value[:14]))

    def test_constant_prices_gives_nan_or_50(self):
        # All same price → no gain/loss → RSI undefined or 50
        flat = [100.0] * 30
        r = rsi(flat, length=14)
        valid = r.value[~np.isnan(r.value)]
        # Should be 50 or NaN (depending on division-by-zero handling)
        assert all(np.isnan(v) or abs(v - 50) < 1e-6 for v in valid)

    def test_always_rising_gives_100(self):
        rising = list(range(1, 51))
        r = rsi(rising, length=14)
        assert r.value[-1] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

class TestMacd:
    def test_outputs(self):
        r = macd(CLOSE, fast=12, slow=26, signal=9)
        assert "macd" in r.arrays
        assert "signal" in r.arrays
        assert "histogram" in r.arrays

    def test_histogram_equals_macd_minus_signal(self):
        r = macd(CLOSE)
        valid = ~(np.isnan(r.arrays["macd"]) | np.isnan(r.arrays["signal"]))
        diff = r.arrays["macd"][valid] - r.arrays["signal"][valid]
        assert np.allclose(diff, r.arrays["histogram"][valid], atol=1e-10)

    def test_correct_length(self):
        r = macd(CLOSE)
        assert len(r.arrays["macd"]) == len(CLOSE)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class TestAtr:
    def test_non_negative(self):
        r = atr(HIGH, LOW, CLOSE, length=14)
        valid = r.value[~np.isnan(r.value)]
        assert np.all(valid >= 0)

    def test_nan_prefix(self):
        r = atr(HIGH, LOW, CLOSE, length=14)
        assert np.all(np.isnan(r.value[:14]))


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollingerBands:
    def test_upper_above_lower(self):
        r = bollinger_bands(CLOSE, length=20, std_dev=2.0)
        valid = ~(np.isnan(r.arrays["upper"]) | np.isnan(r.arrays["lower"]))
        assert np.all(r.arrays["upper"][valid] >= r.arrays["lower"][valid])

    def test_mid_between_bands(self):
        r = bollinger_bands(CLOSE, length=20, std_dev=2.0)
        valid = ~(np.isnan(r.arrays["upper"]) | np.isnan(r.arrays["lower"]) | np.isnan(r.arrays["mid"]))
        assert np.all(r.arrays["upper"][valid] >= r.arrays["mid"][valid])
        assert np.all(r.arrays["mid"][valid] >= r.arrays["lower"][valid])


# ---------------------------------------------------------------------------
# Stochastic
# ---------------------------------------------------------------------------

class TestStochastic:
    def test_k_range(self):
        r = stochastic(HIGH, LOW, CLOSE)
        valid = r.arrays["k"][~np.isnan(r.arrays["k"])]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)

    def test_d_range(self):
        r = stochastic(HIGH, LOW, CLOSE)
        valid = r.arrays["d"][~np.isnan(r.arrays["d"])]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)


# ---------------------------------------------------------------------------
# CCI
# ---------------------------------------------------------------------------

class TestCci:
    def test_returns_result(self):
        r = cci(HIGH, LOW, CLOSE, length=20)
        assert isinstance(r, IndicatorResult)
        assert len(r.value) == len(CLOSE)


# ---------------------------------------------------------------------------
# ROC
# ---------------------------------------------------------------------------

class TestRoc:
    def test_zero_change_gives_zero(self):
        flat = [100.0] * 30
        r = roc(flat, length=10)
        valid = r.value[~np.isnan(r.value)]
        assert np.all(np.abs(valid) < 1e-9)

    def test_known_value(self):
        # price doubles after 10 bars → ROC = 100%
        closes = [100.0] * 10 + [200.0]
        r = roc(closes, length=10)
        assert r.value[-1] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Williams %R
# ---------------------------------------------------------------------------

class TestWilliamsR:
    def test_range(self):
        r = williams_r(HIGH, LOW, CLOSE, length=14)
        valid = r.value[~np.isnan(r.value)]
        assert np.all(valid >= -100)
        assert np.all(valid <= 0)


# ---------------------------------------------------------------------------
# OBV
# ---------------------------------------------------------------------------

class TestObv:
    def test_no_nan(self):
        r = obv(CLOSE, VOLUME)
        assert not np.any(np.isnan(r.value))

    def test_monotone_rising_prices_monotone_obv(self):
        close = _prices(20)
        vol = np.ones(20) * 1000
        r = obv(close, vol)
        assert np.all(np.diff(r.value[1:]) == 1000)


# ---------------------------------------------------------------------------
# Donchian Channels
# ---------------------------------------------------------------------------

class TestDonchian:
    def test_upper_gte_lower(self):
        r = donchian_channels(HIGH, LOW, length=20)
        valid = ~(np.isnan(r.arrays["upper"]) | np.isnan(r.arrays["lower"]))
        assert np.all(r.arrays["upper"][valid] >= r.arrays["lower"][valid])


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------

class TestSupertrend:
    def test_direction_values(self):
        r = supertrend(HIGH, LOW, CLOSE)
        valid = r.arrays["direction"][~np.isnan(r.arrays["direction"])]
        assert set(valid).issubset({-1.0, 1.0, 0.0})


# ---------------------------------------------------------------------------
# IndicatorRegistry
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_registry_has_native_indicators(self):
        assert "rsi" in registry
        assert "macd" in registry
        assert "bbands" in registry
        assert "atr" in registry
        assert "obv" in registry

    def test_compute_rsi(self):
        r = registry.compute("rsi", close=CLOSE, length=14)
        assert isinstance(r, IndicatorResult)

    def test_compute_macd(self):
        r = registry.compute("macd", close=CLOSE, fast=12, slow=26, signal=9)
        assert "macd" in r.arrays

    def test_compute_bbands(self):
        r = registry.compute("bbands", close=CLOSE, length=20, std_dev=2.0)
        assert "upper" in r.arrays

    def test_unknown_indicator_raises(self):
        with pytest.raises((KeyError, Exception)):
            registry.compute("nonexistent_indicator_xyz", close=CLOSE)

    def test_list_indicators(self):
        all_meta = registry.list_indicators()
        assert len(all_meta) >= 30

    def test_list_indicators_by_category(self):
        vol_meta = registry.list_indicators(category="volatility")
        assert all(m.category == "volatility" for m in vol_meta)
        assert len(vol_meta) >= 4

    def test_categories(self):
        cats = registry.categories()
        assert "trend" in cats
        assert "momentum" in cats
        assert "volatility" in cats
        assert "volume" in cats

    def test_to_dict_no_nan(self):
        r = registry.compute("rsi", close=CLOSE, length=14)
        d = r.to_dict()
        assert "value" in d
        # NaN should be serialised as None
        assert all(v is None or isinstance(v, float) for v in d["value"])
