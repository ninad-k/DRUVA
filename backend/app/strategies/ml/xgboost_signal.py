from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

try:
    import xgboost as xgb
    _XGB_AVAILABLE = True
except ImportError:  # pragma: no cover
    xgb = None  # type: ignore[assignment]
    _XGB_AVAILABLE = False

from app.infrastructure.logging import get_logger
from app.strategies.ml.base_ml import FeatureSpec, MLStrategy, Prediction
from app.strategies.registry import register_strategy

logger = get_logger(__name__)


class DummyModel:
    def predict(self, features: np.ndarray) -> Prediction:
        return Prediction(signal="HOLD", probability=0.0)


@register_strategy("ml.xgboost_signal.v1")
class XGBoostSignalStrategy(MLStrategy):
    feature_spec = FeatureSpec(
        features=["ret_1", "ret_5", "rsi_14", "macd_hist"],
        lookback=60,
        timeframe="1m",
    )

    def load_model(self, version: str) -> Any:
        model_path = Path(__file__).resolve().parent / "models" / "xgboost_signal" / version / "model.json"
        if not _XGB_AVAILABLE or not model_path.exists():
            if not _XGB_AVAILABLE:
                logger.warning("ml.xgboost_unavailable", reason="xgboost not installed")
            else:
                logger.warning("ml.model_missing", path=str(model_path))
            return DummyModel()
        booster = xgb.Booster()
        booster.load_model(str(model_path))
        return booster

    def predict(self, features: np.ndarray) -> Prediction:
        if isinstance(self._model, DummyModel):
            return self._model.predict(features)
        matrix = xgb.DMatrix(features.reshape(1, -1))
        out = self._model.predict(matrix)  # type: ignore[union-attr]
        prob_buy = float(out[0])
        if prob_buy > 0.55:
            return Prediction(signal="BUY", probability=prob_buy)
        if prob_buy < 0.45:
            return Prediction(signal="SELL", probability=1.0 - prob_buy)
        return Prediction(signal="HOLD", probability=max(prob_buy, 1.0 - prob_buy))
