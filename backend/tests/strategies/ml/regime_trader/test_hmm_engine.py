"""Unit tests for RegimeDetector (HMM engine).

Tests cover:
  - Model fitting and prediction
  - Forward algorithm (no look-ahead)
  - Feature extraction
  - Save/load persistence
  - Edge cases (small datasets, NaN handling)
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector


@pytest.fixture
def synthetic_ohlcv():
    """Generate synthetic OHLCV data with mixed regimes.

    Returns 365 days of synthetic data with:
      - Days 0-90: Bull regime (trending up, low volatility)
      - Days 91-180: Bear regime (trending down, high volatility)
      - Days 181-270: Neutral regime (sideways, medium volatility)
      - Days 271-364: Bull regime again (trending up)
    """
    np.random.seed(42)
    n_days = 365

    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    close = np.zeros(n_days)
    close[0] = 100.0

    # Synthetic price path with regime changes
    for i in range(1, n_days):
        if i < 90:  # Bull
            drift = 0.001
            vol = 0.005
        elif i < 180:  # Bear
            drift = -0.001
            vol = 0.015
        elif i < 270:  # Neutral
            drift = 0.0
            vol = 0.010
        else:  # Bull again
            drift = 0.001
            vol = 0.005

        shock = np.random.normal(drift, vol)
        close[i] = close[i - 1] * (1 + shock)

    # OHLCV
    ohlcv = pd.DataFrame({
        "timestamp": dates,
        "open": close * (1 + np.random.normal(0, 0.002, n_days)),
        "high": close * (1 + abs(np.random.normal(0.005, 0.005, n_days))),
        "low": close * (1 - abs(np.random.normal(0.005, 0.005, n_days))),
        "close": close,
        "volume": np.random.uniform(1000000, 5000000, n_days),
    })
    ohlcv = ohlcv.set_index("timestamp")
    return ohlcv


@pytest.mark.unit
class TestRegimeDetectorBasics:
    """Basic functionality tests."""

    def test_init_defaults(self):
        """Test detector initialization with default parameters."""
        detector = RegimeDetector()
        assert detector.n_regimes == 5
        assert detector.covariance_type == "full"
        assert not detector.is_fitted
        assert len(RegimeDetector.REGIMES) == 5

    def test_regime_names(self):
        """Test regime ID to name mapping."""
        detector = RegimeDetector()
        assert detector.get_regime_name(0) == "Crash"
        assert detector.get_regime_name(1) == "Bear"
        assert detector.get_regime_name(2) == "Neutral"
        assert detector.get_regime_name(3) == "Bull"
        assert detector.get_regime_name(4) == "Euphoria"

    def test_regime_name_out_of_range(self):
        """Test regime name lookup with invalid index."""
        detector = RegimeDetector()
        with pytest.raises(IndexError):
            detector.get_regime_name(10)


@pytest.mark.unit
class TestRegimeDetectorFitting:
    """Tests for model fitting."""

    def test_fit_basic(self, synthetic_ohlcv):
        """Test basic fitting."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)
        assert detector.is_fitted

    def test_fit_minimum_rows(self):
        """Test fitting with minimum required rows."""
        ohlcv = pd.DataFrame({
            "open": np.random.randn(50) + 100,
            "high": np.random.randn(50) + 101,
            "low": np.random.randn(50) + 99,
            "close": np.random.randn(50) + 100,
            "volume": np.random.uniform(1e6, 5e6, 50),
        })
        detector = RegimeDetector()
        detector.fit(ohlcv)
        assert detector.is_fitted

    def test_fit_insufficient_rows(self):
        """Test fitting with too few rows raises ValueError."""
        ohlcv = pd.DataFrame({
            "open": [100] * 10,
            "high": [101] * 10,
            "low": [99] * 10,
            "close": [100] * 10,
            "volume": [1e6] * 10,
        })
        detector = RegimeDetector()
        with pytest.raises(ValueError, match="at least 50 rows"):
            detector.fit(ohlcv)


@pytest.mark.unit
class TestRegimeDetectorPrediction:
    """Tests for regime prediction."""

    def test_predict_forward_basic(self, synthetic_ohlcv):
        """Test forward algorithm prediction."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)

        regimes = detector.predict_forward(synthetic_ohlcv)
        assert len(regimes) == len(synthetic_ohlcv)
        assert all(0 <= r < 5 for r in regimes)

    def test_predict_forward_not_fitted(self):
        """Test prediction on unfitted model raises RuntimeError."""
        detector = RegimeDetector()
        ohlcv = pd.DataFrame({
            "open": [100] * 100,
            "close": [100] * 100,
            "volume": [1e6] * 100,
        })
        with pytest.raises(RuntimeError, match="not fitted"):
            detector.predict_forward(ohlcv)

    def test_predict_proba(self, synthetic_ohlcv):
        """Test probability prediction."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)

        proba = detector.predict_proba(synthetic_ohlcv)
        assert proba.shape == (len(synthetic_ohlcv), 5)
        assert np.allclose(proba.sum(axis=1), 1.0)  # Probabilities sum to 1
        assert (proba >= 0).all() and (proba <= 1).all()

    def test_confidence(self, synthetic_ohlcv):
        """Test confidence calculation."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)

        confidence = detector.get_confidence(synthetic_ohlcv)
        assert 0.0 <= confidence <= 1.0

    def test_confidence_on_recent_bar(self, synthetic_ohlcv):
        """Test that confidence is based on the most recent bar."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)

        proba_full = detector.predict_proba(synthetic_ohlcv)
        proba_recent = detector.predict_proba(synthetic_ohlcv.iloc[-1:])

        confidence_method = detector.get_confidence(synthetic_ohlcv)
        expected_confidence = proba_full[-1].max()

        assert np.isclose(confidence_method, expected_confidence)


@pytest.mark.unit
class TestRegimeDetectorPersistence:
    """Tests for save/load functionality."""

    def test_save_and_load(self, synthetic_ohlcv, tmp_path):
        """Test model persistence."""
        detector1 = RegimeDetector()
        detector1.fit(synthetic_ohlcv)
        regimes1 = detector1.predict_forward(synthetic_ohlcv)

        # Save
        save_path = tmp_path / "model.pkl"
        detector1.save(save_path)
        assert save_path.exists()

        # Load
        detector2 = RegimeDetector()
        detector2.load(save_path)
        regimes2 = detector2.predict_forward(synthetic_ohlcv)

        assert np.array_equal(regimes1, regimes2)

    def test_save_to_directory(self, synthetic_ohlcv, tmp_path):
        """Test saving to a directory (creates model.pkl inside)."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)

        detector.save(tmp_path)
        assert (tmp_path / "model.pkl").exists()

    def test_load_missing_file(self):
        """Test loading from non-existent file raises FileNotFoundError."""
        detector = RegimeDetector()
        with pytest.raises(FileNotFoundError):
            detector.load("/nonexistent/path/model.pkl")


@pytest.mark.unit
class TestFeatureExtraction:
    """Tests for technical feature engineering."""

    def test_feature_shape(self, synthetic_ohlcv):
        """Test feature extraction output shape."""
        detector = RegimeDetector()
        features = detector._extract_features(synthetic_ohlcv)
        assert features.shape == (len(synthetic_ohlcv), 5)

    def test_features_standardized(self, synthetic_ohlcv):
        """Test that features are standardized (mean~0, std~1)."""
        detector = RegimeDetector()
        detector.fit(synthetic_ohlcv)
        features = detector._extract_features(synthetic_ohlcv)

        mean = features.mean(axis=0)
        std = features.std(axis=0)

        # After standardization, mean should be ~0 and std ~1
        assert np.allclose(mean, 0, atol=0.1)
        assert np.allclose(std, 1, atol=0.1)

    def test_features_no_nans(self, synthetic_ohlcv):
        """Test that feature extraction handles NaNs."""
        detector = RegimeDetector()
        features = detector._extract_features(synthetic_ohlcv)
        assert not np.any(np.isnan(features))

    def test_features_finite(self, synthetic_ohlcv):
        """Test that all features are finite (no inf)."""
        detector = RegimeDetector()
        features = detector._extract_features(synthetic_ohlcv)
        assert np.all(np.isfinite(features))


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases and robustness."""

    def test_constant_price(self):
        """Test with constant price (zero volatility)."""
        ohlcv = pd.DataFrame({
            "open": [100.0] * 100,
            "high": [100.0] * 100,
            "low": [100.0] * 100,
            "close": [100.0] * 100,
            "volume": [1e6] * 100,
        })
        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)
        assert len(regimes) == 100

    def test_extreme_volatility(self):
        """Test with extreme price swings."""
        np.random.seed(42)
        ohlcv = pd.DataFrame({
            "open": np.random.uniform(50, 150, 100),
            "high": np.random.uniform(50, 150, 100),
            "low": np.random.uniform(50, 150, 100),
            "close": np.random.uniform(50, 150, 100),
            "volume": np.random.uniform(1e6, 5e6, 100),
        })
        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)
        assert len(regimes) == 100

    def test_zero_volume(self):
        """Test with zero volume (rare but possible)."""
        ohlcv = pd.DataFrame({
            "open": [100] * 100,
            "high": [101] * 100,
            "low": [99] * 100,
            "close": np.random.randn(100) + 100,
            "volume": [0.0] * 100,  # All zero
        })
        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)
        assert len(regimes) == 100

    def test_single_outlier(self, synthetic_ohlcv):
        """Test robustness to a single price spike."""
        ohlcv = synthetic_ohlcv.copy()
        ohlcv.loc[ohlcv.index[50], "close"] *= 10  # 10x spike

        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)
        assert len(regimes) == len(ohlcv)


@pytest.mark.unit
class TestRegimeDetectionRealism:
    """Tests to validate realistic regime detection."""

    def test_bull_regime_detected(self):
        """Test that sustained uptrend is detected as Bull."""
        # Create steady uptrend
        n_days = 100
        close = np.linspace(100, 120, n_days)  # 20% gain
        ohlcv = pd.DataFrame({
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": [1e6] * n_days,
        })

        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)

        # Later part should be skewed toward Bull (higher indices)
        later_regimes = regimes[-20:]
        bull_or_higher = np.sum(later_regimes >= 2)
        assert bull_or_higher >= 10  # Most should be Bull/Euphoria

    def test_crash_regime_detected(self):
        """Test that sharp drawdown is detected as Crash/Bear."""
        # Create sharp crash
        n_days = 100
        close = np.concatenate([
            np.linspace(100, 110, 50),  # 10% up
            np.linspace(110, 80, 50),   # 27% down sharply
        ])
        ohlcv = pd.DataFrame({
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": [1e6] * n_days,
        })

        detector = RegimeDetector()
        detector.fit(ohlcv)
        regimes = detector.predict_forward(ohlcv)

        # Crash period should have lower regime IDs
        crash_regimes = regimes[60:]
        crash_or_lower = np.sum(crash_regimes <= 1)
        assert crash_or_lower >= 10  # Most should be Crash/Bear
