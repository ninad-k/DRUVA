"""Hidden Markov Model engine for volatility regime detection.

This module implements a volatility classifier using HMM with forward inference
to avoid look-ahead bias. Regimes are detected from technical indicators
computed on OHLCV data.

**Regimes** (5-state default):
  - 0: Crash (extreme volatility, sharp drawdown)
  - 1: Bear (high volatility, downtrend)
  - 2: Neutral (medium volatility, sideways)
  - 3: Bull (low volatility, uptrend)
  - 4: Euphoria (low volatility, extreme upside)

**Features**:
  - Returns (1-bar, 5-bar, 20-bar)
  - Volatility (20-bar rolling std)
  - Volume (20-bar rolling mean)
  - These feed into the HMM as multivariate Gaussian emissions.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


class RegimeDetector:
    """HMM-based volatility regime detector.

    Trained on historical OHLCV data; inference uses the forward algorithm
    to ensure no look-ahead bias. States represent distinct market regimes.
    """

    REGIMES = ["Crash", "Bear", "Neutral", "Bull", "Euphoria"]

    def __init__(
        self,
        n_regimes: int = 5,
        covariance_type: str = "full",
        random_state: int = 42,
    ):
        """Initialize HMM model.

        Args:
            n_regimes: Number of hidden states (default 5)
            covariance_type: HMM covariance type ("full", "tied", "diag", "spherical")
            random_state: Seed for reproducibility
        """
        self.n_regimes = n_regimes
        self.covariance_type = covariance_type
        self.random_state = random_state

        self.model = hmm.GaussianHMM(
            n_components=n_regimes,
            covariance_type=covariance_type,
            n_iter=1000,
            random_state=random_state,
        )
        self.scaler = StandardScaler()
        self.is_fitted = False

    def fit(self, ohlcv: pd.DataFrame) -> None:
        """Train HMM on historical OHLCV data.

        Args:
            ohlcv: DataFrame with columns ['open', 'high', 'low', 'close', 'volume'].
                   Expects at least 252 rows (1 year of daily data).

        Raises:
            ValueError: If ohlcv has fewer than 50 rows.
        """
        if len(ohlcv) < 50:
            raise ValueError(f"Fit requires at least 50 rows; got {len(ohlcv)}")

        features = self._extract_features(ohlcv)
        logger.info("hmm.fit", rows=len(features), features=features.shape[1])

        self.model.fit(features)
        self.is_fitted = True
        logger.info("hmm.fitted", n_regimes=self.n_regimes)

    def predict_forward(self, ohlcv: pd.DataFrame) -> np.ndarray:
        """Predict regimes using forward algorithm (no look-ahead).

        The forward algorithm computes the most likely regime at each step
        without "peeking" at future data.

        Args:
            ohlcv: Historical OHLCV data (at least lookback rows).

        Returns:
            Array of regime indices [0, n_regimes-1], length = len(ohlcv).

        Raises:
            RuntimeError: If model not fitted.
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        features = self._extract_features(ohlcv)
        regimes = self.model.predict(features)
        return regimes

    def predict_proba(self, ohlcv: pd.DataFrame) -> np.ndarray:
        """Predict regime probabilities (posterior).

        Args:
            ohlcv: Historical OHLCV data.

        Returns:
            Array of shape (n_samples, n_regimes) with probabilities per regime.

        Raises:
            RuntimeError: If model not fitted.
        """
        if not self.is_fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        features = self._extract_features(ohlcv)
        return self.model.predict_proba(features)

    def get_confidence(self, ohlcv: pd.DataFrame) -> float:
        """Get model confidence on the most recent bar.

        Confidence = max(probabilities) for the last regime.

        Args:
            ohlcv: Historical OHLCV data.

        Returns:
            Float in [0, 1] representing confidence in the current regime.
        """
        proba = self.predict_proba(ohlcv)
        if len(proba) == 0:
            return 0.0
        return float(proba[-1].max())

    def get_regime_name(self, regime_idx: int) -> str:
        """Map regime index to human-readable name.

        Args:
            regime_idx: Integer regime ID (0 to n_regimes-1).

        Returns:
            Regime name (e.g., "Bull", "Crash").

        Raises:
            IndexError: If regime_idx is out of range.
        """
        if regime_idx < 0 or regime_idx >= len(self.REGIMES):
            raise IndexError(
                f"Regime {regime_idx} out of range [0, {len(self.REGIMES) - 1}]"
            )
        return self.REGIMES[regime_idx]

    def save(self, path: str | Path) -> None:
        """Save fitted model and scaler to disk.

        Args:
            path: Directory or .pkl file path. If directory, creates 'model.pkl'.
        """
        path = Path(path)
        if path.is_dir():
            path = path / "model.pkl"
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "wb") as f:
            pickle.dump({"model": self.model, "scaler": self.scaler}, f)
        logger.info("hmm.saved", path=str(path))

    def load(self, path: str | Path) -> None:
        """Load fitted model and scaler from disk.

        Args:
            path: Path to .pkl file or directory containing 'model.pkl'.
        """
        path = Path(path)
        if path.is_dir():
            path = path / "model.pkl"

        if not path.exists():
            raise FileNotFoundError(f"Model not found at {path}")

        with open(path, "rb") as f:
            data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data["scaler"]
        self.is_fitted = True
        logger.info("hmm.loaded", path=str(path))

    # ---- Private feature engineering ----------------------------------------

    def _extract_features(self, ohlcv: pd.DataFrame) -> np.ndarray:
        """Extract technical features from OHLCV.

        Features:
          1. 1-bar log return
          2. 5-bar log return
          3. 20-bar log return
          4. 20-bar rolling volatility (std of returns)
          5. 20-bar rolling average volume (normalized)

        Args:
            ohlcv: DataFrame with ['close', 'volume'].

        Returns:
            Standardized feature matrix of shape (n_samples, 5).
        """
        close = ohlcv["close"].astype(float).values
        volume = ohlcv["volume"].astype(float).values

        # Log returns
        log_returns = np.diff(np.log(close), prepend=np.log(close[0]))
        ret_1bar = log_returns
        ret_5bar = pd.Series(log_returns).rolling(5).sum().values
        ret_20bar = pd.Series(log_returns).rolling(20).sum().values

        # Volatility and volume
        volatility = pd.Series(log_returns).rolling(20).std().values
        volume_ma = pd.Series(volume).rolling(20).mean().values
        volume_ma = np.where(volume_ma > 0, volume_ma, 1.0)  # Avoid log(0)
        volume_norm = np.log(volume_ma)

        # Stack and replace NaNs
        features = np.column_stack([ret_1bar, ret_5bar, ret_20bar, volatility, volume_norm])
        features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

        # Fit or transform with scaler
        if not self.is_fitted:
            features = self.scaler.fit_transform(features)
        else:
            features = self.scaler.transform(features)

        return features
