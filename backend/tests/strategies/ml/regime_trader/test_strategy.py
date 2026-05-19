"""Unit tests for RegimeTraderStrategy (MLStrategy plugin).

Tests cover:
  - Strategy initialization and registration
  - Feature building
  - Prediction and signal generation
  - Stability filter (persistence, flickering)
  - Metadata accuracy
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector
from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy
from app.strategies.registry import all_strategies, get_strategy_class


@pytest.fixture
def synthetic_ohlcv():
    """Generate synthetic OHLCV for testing."""
    np.random.seed(42)
    n_days = 252
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    close = np.random.randn(n_days).cumsum() + 100
    ohlcv = pd.DataFrame({
        "timestamp": dates,
        "open": close,
        "high": close + abs(np.random.randn(n_days)),
        "low": close - abs(np.random.randn(n_days)),
        "close": close,
        "volume": np.random.uniform(1e6, 5e6, n_days),
    })
    return ohlcv.set_index("timestamp")


@pytest.fixture
def fitted_detector(synthetic_ohlcv):
    """Create a fitted detector for testing."""
    detector = RegimeDetector()
    detector.fit(synthetic_ohlcv)
    return detector


@pytest.mark.unit
class TestRegimeTraderStrategyBasics:
    """Basic strategy functionality tests."""

    def test_strategy_registered(self):
        """Test that strategy is auto-registered."""
        strategies = all_strategies()
        assert "regime_trader.hmm.v1" in strategies

    def test_strategy_instantiation(self):
        """Test strategy creation."""
        strategy = RegimeTraderStrategy(
            id="test_strategy",
            account_id="test_account",
        )
        assert strategy.id == "test_strategy"
        assert strategy.account_id == "test_account"

    def test_feature_spec(self):
        """Test feature specification."""
        strategy = RegimeTraderStrategy(
            id="test",
            account_id="test_account",
        )
        assert strategy.feature_spec.lookback == 252
        assert strategy.feature_spec.timeframe == "1d"
        assert "close" in strategy.feature_spec.features
        assert "volume" in strategy.feature_spec.features

    def test_parameters_override(self):
        """Test parameter customization."""
        params = {
            "allocations": {0: 0.1, 1: 0.2, 2: 0.5, 3: 1.0, 4: 0.9},
            "confidence_threshold": 0.70,
            "max_flickers": 3,
        }
        strategy = RegimeTraderStrategy(
            id="test",
            account_id="test_account",
            parameters=params,
        )
        assert strategy.allocations[3] == 1.0
        assert strategy.confidence_threshold == 0.70
        assert strategy.max_flickers == 3


@pytest.mark.unit
class TestFeatureBuilding:
    """Tests for feature building from candles."""

    def test_build_features_shape(self):
        """Test feature matrix shape."""
        # Create mock candles
        candles = []
        for i in range(100):
            candle = MagicMock()
            candle.close = 100.0 + i * 0.5
            candle.volume = 1e6
            candles.append(candle)

        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        features = strategy.build_features(candles)

        assert features.shape == (100, 2)
        assert features[:, 0].min() > 0  # Close prices positive
        assert features[:, 1].min() > 0  # Volume positive

    def test_build_features_values(self):
        """Test that features are extracted correctly."""
        candles = []
        expected_close = [100.0, 101.0, 102.0]
        expected_volume = [1e6, 2e6, 3e6]

        for close, volume in zip(expected_close, expected_volume):
            candle = MagicMock()
            candle.close = close
            candle.volume = volume
            candles.append(candle)

        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        features = strategy.build_features(candles)

        assert np.allclose(features[:, 0], expected_close)
        assert np.allclose(features[:, 1], expected_volume)


@pytest.mark.unit
class TestRegimeHistory:
    """Tests for stability filter (persistence and flickering)."""

    def test_persistence_tracking(self, fitted_detector):
        """Test that persistence_bars is tracked correctly."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        # Simulate regime staying same
        regimes = np.array([2, 2, 2, 1, 1])
        for regime in regimes:
            strategy._update_regime_history(regime, regimes)

        assert strategy.persistence_bars >= 1

    def test_flickering_detection(self, fitted_detector):
        """Test that flickering is detected."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        # Simulate rapid regime changes
        regimes = np.array([2, 1, 2, 1, 2, 1, 2])
        for regime in regimes:
            strategy._update_regime_history(regime, regimes)

        # Should have detected multiple switches
        assert strategy.flicker_count >= 3

    def test_max_flickering_threshold(self, fitted_detector):
        """Test flickering warning threshold."""
        params = {"max_flickers": 2}
        strategy = RegimeTraderStrategy(
            id="test",
            account_id="test_account",
            parameters=params,
        )
        strategy.detector = fitted_detector
        strategy.max_flickers = 2

        regimes = np.array([2, 1, 2, 1, 2, 1, 2])
        for regime in regimes:
            strategy._update_regime_history(regime, regimes)

        assert strategy.flicker_count > strategy.max_flickers


@pytest.mark.unit
class TestSignalGeneration:
    """Tests for signal computation."""

    def test_signal_low_confidence(self, fitted_detector):
        """Test that HOLD signal is emitted when confidence is low."""
        strategy = RegimeTraderStrategy(
            id="test",
            account_id="test_account",
            parameters={"confidence_threshold": 0.80},
        )
        strategy.detector = fitted_detector

        # Low confidence case
        signal, prob = strategy._compute_signal(regime=3, confidence=0.50)
        assert signal == "HOLD"

    def test_signal_buy_bull_regime(self, fitted_detector):
        """Test BUY signal in Bull regime with persistence."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        # Simulate stable Bull regime
        strategy.last_regime = 3
        strategy.persistence_bars = 5

        signal, prob = strategy._compute_signal(regime=3, confidence=0.75)
        assert signal == "BUY"

    def test_signal_sell_crash_regime(self, fitted_detector):
        """Test SELL signal in Crash regime."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        strategy.last_regime = 0
        strategy.persistence_bars = 5

        signal, prob = strategy._compute_signal(regime=0, confidence=0.75)
        assert signal == "SELL"

    def test_signal_insufficient_persistence(self, fitted_detector):
        """Test HOLD when persistence < 3 bars."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        strategy.last_regime = 3
        strategy.persistence_bars = 1  # Too early

        signal, prob = strategy._compute_signal(regime=3, confidence=0.75)
        assert signal == "HOLD"


@pytest.mark.unit
class TestPrediction:
    """Tests for full prediction pipeline."""

    def test_prediction_metadata(self, fitted_detector, synthetic_ohlcv):
        """Test that prediction includes correct metadata."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        # Create feature array
        close = synthetic_ohlcv["close"].values
        volume = synthetic_ohlcv["volume"].values
        features = np.column_stack([close, volume])

        prediction = strategy.predict(features)

        # Check metadata
        assert "regime_name" in prediction.meta
        assert "regime_id" in prediction.meta
        assert "confidence" in prediction.meta
        assert "allocation_pct" in prediction.meta
        assert "leverage" in prediction.meta
        assert "persistence_bars" in prediction.meta
        assert "flicker_warning" in prediction.meta

    def test_prediction_allocation_mapping(self, fitted_detector, synthetic_ohlcv):
        """Test that allocation matches regime."""
        allocations = {0: 0.05, 1: 0.3, 2: 0.5, 3: 0.95, 4: 0.8}
        strategy = RegimeTraderStrategy(
            id="test",
            account_id="test_account",
            parameters={"allocations": allocations},
        )
        strategy.detector = fitted_detector

        features = np.column_stack([
            synthetic_ohlcv["close"].values,
            synthetic_ohlcv["volume"].values,
        ])
        prediction = strategy.predict(features)

        regime_id = prediction.meta["regime_id"]
        expected_allocation = allocations[regime_id] * 100
        assert np.isclose(prediction.meta["allocation_pct"], expected_allocation)

    def test_prediction_confidence_in_range(self, fitted_detector, synthetic_ohlcv):
        """Test that confidence is in valid range."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        features = np.column_stack([
            synthetic_ohlcv["close"].values,
            synthetic_ohlcv["volume"].values,
        ])
        prediction = strategy.predict(features)

        confidence = prediction.meta["confidence"]
        assert 0.0 <= confidence <= 1.0


@pytest.mark.unit
class TestModelLoading:
    """Tests for model loading contract."""

    def test_load_model_missing_file(self):
        """Test loading missing model returns detector (not raises)."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")

        # Should not raise, just log warning
        detector = strategy.load_model("nonexistent_version")
        assert isinstance(detector, RegimeDetector)

    def test_load_model_existing_file(self, synthetic_ohlcv, tmp_path):
        """Test loading existing model file."""
        # Create and save a model
        original_detector = RegimeDetector()
        original_detector.fit(synthetic_ohlcv)
        save_path = tmp_path / "model.pkl"
        original_detector.save(save_path)

        # Patch the path to use our temp dir
        with patch(
            "pathlib.Path.resolve",
            return_value=tmp_path.parent,
        ):
            strategy = RegimeTraderStrategy(id="test", account_id="test_account")
            detector = strategy.load_model(str(save_path.parent.name))

            # Should load successfully
            assert detector.is_fitted


@pytest.mark.unit
class TestEdgeCases:
    """Edge case tests."""

    def test_predict_without_detector(self):
        """Test prediction when detector is None."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = None

        features = np.array([[100, 1e6], [101, 2e6]])
        prediction = strategy.predict(features)

        assert prediction.signal == "HOLD"
        assert prediction.probability == 0.0
        assert "error" in prediction.meta

    def test_predict_invalid_features_shape(self, fitted_detector):
        """Test prediction with invalid feature shape."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        # Wrong shape
        features = np.array([100, 101, 102])

        prediction = strategy.predict(features)
        assert prediction.signal == "HOLD"

    def test_regime_name_consistency(self, fitted_detector, synthetic_ohlcv):
        """Test that regime names match detector."""
        strategy = RegimeTraderStrategy(id="test", account_id="test_account")
        strategy.detector = fitted_detector

        features = np.column_stack([
            synthetic_ohlcv["close"].values,
            synthetic_ohlcv["volume"].values,
        ])
        prediction = strategy.predict(features)

        regime_id = prediction.meta["regime_id"]
        regime_name = prediction.meta["regime_name"]

        assert regime_name == RegimeDetector.REGIMES[regime_id]
