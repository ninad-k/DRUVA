"""Regime-Trader strategy: MLStrategy plugin using HMM regime detection.

This is the integration point between the HMM engine and DRUVA's execution system.
It implements MLStrategy and registers itself with the auto-discovery registry.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.infrastructure.logging import get_logger
from app.strategies.ml.base_ml import FeatureSpec, MLStrategy, Prediction
from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector
from app.strategies.registry import register_strategy

logger = get_logger(__name__)

# Regime-to-allocation mapping (can be overridden via parameters)
DEFAULT_ALLOCATIONS = {
    0: 0.05,   # Crash: 5%
    1: 0.30,   # Bear: 30%
    2: 0.50,   # Neutral: 50%
    3: 0.95,   # Bull: 95%
    4: 0.80,   # Euphoria: 80%
}

DEFAULT_LEVERAGE = {
    0: 1.0,    # Crash: no leverage
    1: 1.0,    # Bear: no leverage
    2: 1.0,    # Neutral: no leverage
    3: 1.25,   # Bull: 1.25x leverage
    4: 1.0,    # Euphoria: no leverage (already at peak)
}


@register_strategy("regime_trader.hmm.v1")
class RegimeTraderStrategy(MLStrategy):
    """HMM-based volatility regime detector.

    Emits allocation recommendations and regime/confidence metadata.
    Does NOT emit BUY/SELL signals directly; instead, it guides the risk
    manager and portfolio allocator on position sizing.

    **Signal interpretation**:
      - "BUY" → Increase exposure to the current regime's allocation
      - "SELL" → Decrease exposure (regime downgrades)
      - "HOLD" → Stay in current regime (confidence too low for change)

    **Metadata returned**:
      - regime_name: Human-readable regime ("Bull", "Crash", etc.)
      - regime_id: Integer [0, 4]
      - confidence: Float [0, 1] in current regime
      - allocation_pct: Recommended % of portfolio
      - leverage: Recommended leverage multiplier
      - persistence_bars: How many bars current regime has persisted
      - flicker_warning: True if flickering detected (> 4 switches in 20 bars)
    """

    feature_spec = FeatureSpec(
        features=["close", "volume"],
        lookback=252,  # 1 year of daily data for training/detection
        timeframe="1d",  # Daily bars
    )

    def __init__(
        self,
        *,
        id: str,
        account_id: str,
        parameters: dict[str, Any] | None = None,
    ):
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self.detector: RegimeDetector | None = None

        # Stability filter: track regime history
        self.regime_history: deque[int] = deque(maxlen=20)
        self.last_regime: int | None = None
        self.persistence_bars = 0
        self.flicker_count = 0

        # Allocation overrides from parameters
        self.allocations = parameters.get("allocations", DEFAULT_ALLOCATIONS) if parameters else DEFAULT_ALLOCATIONS
        self.leverage = parameters.get("leverage", DEFAULT_LEVERAGE) if parameters else DEFAULT_LEVERAGE

        # Confidence threshold for regime changes
        self.confidence_threshold = float(
            parameters.get("confidence_threshold", 0.60) if parameters else 0.60
        )

        # Flickering detection: max allowed regime switches in 20-bar window
        self.max_flickers = int(parameters.get("max_flickers", 4) if parameters else 4)

    # ---- Contract implementation -------------------------------------------

    @property
    def feature_spec(self) -> FeatureSpec:
        return FeatureSpec(
            features=["close", "volume"],
            lookback=252,
            timeframe="1d",
        )

    def load_model(self, version: str) -> Any:
        """Load pre-trained HMM model.

        Looks for models in `backend/app/strategies/ml/regime_trader/models/{version}/model.pkl`.
        If not found, returns an unfit detector (training will happen on first candle batch).
        """
        model_dir = Path(__file__).resolve().parent / "models" / version
        model_file = model_dir / "model.pkl"

        detector = RegimeDetector(n_regimes=5)

        if model_file.exists():
            detector.load(model_file)
            logger.info(
                "regime_trader.model_loaded",
                version=version,
                path=str(model_file),
            )
        else:
            logger.warning(
                "regime_trader.model_not_found",
                version=version,
                path=str(model_file),
                note="Will auto-fit on first batch of candles",
            )

        return detector

    def predict(self, features: np.ndarray) -> Prediction:
        """Detect regime from feature vector and emit allocation signal.

        Args:
            features: Feature matrix from build_features (n_samples, 2: [close, volume]).

        Returns:
            Prediction with signal="BUY"/"SELL"/"HOLD" and metadata dict.
        """
        if self.detector is None:
            return Prediction(
                signal="HOLD",
                probability=0.0,
                meta={"error": "detector not initialized"},
            )

        # Convert feature vector back to DataFrame for detector
        # (build_features returns raw [close, volume]; we need to reconstruct OHLCV)
        # For now, assume features is actually the full OHLCV passed from on_candle
        if isinstance(features, np.ndarray) and features.shape[1] >= 2:
            close = features[:, 0]
            volume = features[:, 1]
            ohlcv = pd.DataFrame({
                "close": close,
                "volume": volume,
            })
        else:
            logger.error("regime_trader.invalid_features", shape=features.shape)
            return Prediction(signal="HOLD", probability=0.0)

        # Predict regimes
        regimes = self.detector.predict_forward(ohlcv)
        confidence = self.detector.get_confidence(ohlcv)
        current_regime = int(regimes[-1])

        # Stability filter
        self._update_regime_history(current_regime, regimes)

        # Get allocation for this regime
        allocation = self.allocations.get(current_regime, 0.50)
        leverage = self.leverage.get(current_regime, 1.0)

        # Determine signal
        signal, signal_confidence = self._compute_signal(current_regime, confidence)

        regime_name = RegimeDetector.REGIMES[current_regime]
        meta = {
            "regime_name": regime_name,
            "regime_id": current_regime,
            "confidence": float(confidence),
            "allocation_pct": float(allocation * 100),
            "leverage": float(leverage),
            "persistence_bars": self.persistence_bars,
            "flicker_warning": self.flicker_count > self.max_flickers,
            "flicker_count": self.flicker_count,
        }

        logger.info(
            "regime_trader.prediction",
            regime=regime_name,
            confidence=f"{confidence:.3f}",
            allocation=f"{allocation:.1%}",
            persistence=self.persistence_bars,
            signal=signal,
        )

        return Prediction(signal=signal, probability=signal_confidence, meta=meta)

    # ---- Feature building (override default) --------------------------------

    def build_features(self, candles: list) -> np.ndarray:
        """Build OHLCV array from candle list.

        Args:
            candles: List of Candle objects from StrategyContext.

        Returns:
            Feature matrix of shape (n_candles, 2) with [close, volume].
        """
        # Reconstruct full OHLCV for detector
        close = np.array([float(c.close) for c in candles], dtype=np.float64)
        volume = np.array([float(c.volume) for c in candles], dtype=np.float64)

        # Return as 2D array (close, volume per row)
        return np.column_stack([close, volume])

    # ---- Private helpers ---------------------------------------------------

    def _update_regime_history(self, current_regime: int, all_regimes: np.ndarray) -> None:
        """Update stability filter state.

        Tracks:
          - persistence_bars: consecutive bars in same regime
          - flicker_count: number of regime switches in the last 20 bars
        """
        self.regime_history.append(current_regime)

        if self.last_regime is None:
            self.last_regime = current_regime
            self.persistence_bars = 1
            self.flicker_count = 0
        elif current_regime == self.last_regime:
            self.persistence_bars += 1
        else:
            # Regime changed
            self.last_regime = current_regime
            self.persistence_bars = 1
            self.flicker_count += 1

        # Log warning if flickering
        if len(self.regime_history) >= 20 and self.flicker_count > self.max_flickers:
            logger.warning(
                "regime_trader.flickering",
                flicker_count=self.flicker_count,
                in_bars=len(self.regime_history),
                threshold=self.max_flickers,
            )

    def _compute_signal(self, regime: int, confidence: float) -> tuple[str, float]:
        """Determine signal based on regime and confidence.

        Strategy:
          - If persistence >= 3 bars and confidence >= threshold → "BUY" (increase exposure)
          - If regime is low-allocation (Crash/Bear) → "SELL" (reduce exposure)
          - Otherwise → "HOLD"

        Args:
            regime: Current regime ID
            confidence: Model confidence [0, 1]

        Returns:
            (signal: "BUY"/"SELL"/"HOLD", probability: float)
        """
        if confidence < self.confidence_threshold:
            return "HOLD", 0.5

        # If we've been stable in this regime, consider increasing exposure
        if self.persistence_bars >= 3:
            if regime in [3, 4]:  # Bull, Euphoria
                return "BUY", confidence
            elif regime in [0, 1]:  # Crash, Bear
                return "SELL", confidence
            else:  # Neutral
                return "HOLD", 0.5

        return "HOLD", 0.5
