"""Base class and supporting types for ML strategies.

See ``README.md`` in this folder for the full plugin contract.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

import numpy as np

from app.strategies.base import Candle, Signal, Strategy, StrategyContext

SignalClass = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class FeatureSpec:
    """Declarative description of the features a model consumes."""

    features: list[str]
    lookback: int                         # number of past candles required
    timeframe: str = "1m"                 # candle timeframe expected
    transforms: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Prediction:
    """Output of :meth:`MLStrategy.predict`."""

    signal: SignalClass
    probability: float                    # 0.0 – 1.0
    meta: dict[str, Any] = field(default_factory=dict)


class MLStrategy(Strategy):
    """Abstract base for all ML-powered strategies.

    Subclasses must implement :meth:`load_model` and :meth:`predict`, and must
    set :attr:`feature_spec`. :meth:`on_candle` is implemented here — it builds
    the feature vector, calls :meth:`predict`, and converts the prediction into
    a :class:`~app.strategies.base.Signal`.
    """

    feature_spec: FeatureSpec
    model_version: str = "latest"
    default_quantity: Decimal = Decimal("1")
    min_confidence: float = 0.55

    def __init__(
        self,
        *,
        id: str,
        account_id: str,
        parameters: dict[str, Any] | None = None,
    ):
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self._model: Any = None

    # ---- Contract for subclasses ----------------------------------------
    @abstractmethod
    def load_model(self, version: str) -> Any:
        """Load and return the model artifact for the given ``version``."""

    @abstractmethod
    def predict(self, features: np.ndarray) -> Prediction:
        """Run inference on a pre-built feature vector and return a :class:`Prediction`."""

    # ---- Engine-facing implementation -----------------------------------
    async def on_start(self, context: StrategyContext) -> None:
        """Load the model artifact once when the strategy is enabled."""
        self._model = self.load_model(self.model_version)

    async def on_candle(
        self,
        candle: Candle,
        context: StrategyContext,
    ) -> Signal | None:
        """Default pipeline: fetch lookback → build features → predict → emit signal."""
        candles = await context.get_candles(
            symbol=candle.symbol,
            timeframe=self.feature_spec.timeframe,
            limit=self.feature_spec.lookback,
        )
        if len(candles) < self.feature_spec.lookback:
            return None

        features = self.build_features(candles)
        prediction = self.predict(features)

        if prediction.signal == "HOLD":
            return None
        if prediction.probability < self.min_confidence:
            return None

        return Signal(
            symbol=candle.symbol,
            side=prediction.signal,  # type: ignore[arg-type]
            quantity=self.default_quantity,
            reason=f"ml:{self.__class__.__name__}",
            confidence=prediction.probability,
            metadata={"model": self.__class__.__name__, "version": self.model_version},
        )

    # ---- Feature building hook ------------------------------------------
    def build_features(self, candles: list[Candle]) -> np.ndarray:
        """Default implementation: subclass or override to use ``features/builder.py``.

        This default returns a simple close-price vector. Real strategies should
        override with engineered features matching :attr:`feature_spec`.
        """
        return np.array([float(c.close) for c in candles], dtype=np.float64)
