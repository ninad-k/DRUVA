"""FreqAIPipeline — Phase L.

Orchestrates the adaptive ML loop:
  1. ``FeatureKitchen`` builds feature matrix from new candles.
  2. ``DataKitchen`` splits into train/test/live windows.
  3. A sklearn-compatible model is trained on the training window.
  4. ``predict()`` runs the trained model on the latest ``X_live`` row.
  5. The pipeline retriggers training every ``retrain_every`` bars.

NOTE on model persistence: ``pickle`` is used only to persist locally-trained
sklearn model artifacts to ``model_dir``.  The models are trained from DRUVA's
own candle data — never deserialised from untrusted sources.  This matches the
pattern already used in ``app/strategies/ml/regime_trader/hmm_engine.py``.
"""

from __future__ import annotations

import pickle  # noqa: S403 — used for locally-trained sklearn artifacts (trusted)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.strategies.ml.freq_ai.kitchen import (
    DataKitchen,
    FeatureKitchen,
)


ModelKind = Literal["random_forest", "gradient_boost", "logistic", "custom"]


@dataclass
class PipelineConfig:
    """Configuration for FreqAIPipeline."""

    model_kind: ModelKind = "random_forest"
    retrain_every: int = 100
    train_ratio: float = 0.80
    test_ratio: float = 0.10
    live_rows: int = 1
    random_state: int = 42
    model_dir: Path | None = None
    feature_names: list[str] = field(default_factory=list)
    model_params: dict[str, Any] = field(default_factory=dict)


class FreqAIPipeline:
    """Adaptive ML training + prediction pipeline.

    Usage::

        pipeline = FreqAIPipeline(PipelineConfig())
        pipeline.fit(candles, labels)
        signal, prob = pipeline.predict(candles)
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        *,
        custom_model: Any = None,
    ) -> None:
        self._cfg = config or PipelineConfig()
        self._custom_model = custom_model
        self._model: Any = None
        self._kitchen = FeatureKitchen(
            feature_names=self._cfg.feature_names or None,
        )
        self._data_kitchen = DataKitchen(
            train_ratio=self._cfg.train_ratio,
            test_ratio=self._cfg.test_ratio,
            live_rows=self._cfg.live_rows,
        )
        self._bars_since_train = 0
        self._last_metrics: dict[str, float] = {}

    def fit(
        self,
        candles: list[dict[str, float]],
        labels: list[int],
    ) -> dict[str, float]:
        """Train on candle history; return accuracy metrics."""
        features = self._kitchen.build(candles, labels)
        window = self._data_kitchen.split(features)
        model = self._build_model()
        model.fit(window.X_train, window.y_train)
        self._model = model
        self._bars_since_train = 0

        metrics: dict[str, float] = {}
        if len(window.X_test) > 0:
            try:
                metrics["test_accuracy"] = float(model.score(window.X_test, window.y_test))
            except Exception:
                pass
        if len(window.X_train) > 0:
            try:
                metrics["train_accuracy"] = float(model.score(window.X_train, window.y_train))
            except Exception:
                pass
        self._last_metrics = metrics

        if self._cfg.model_dir:
            self._save_model(self._cfg.model_dir)

        return metrics

    def predict(
        self,
        candles: list[dict[str, float]],
        labels: list[int] | None = None,
    ) -> tuple[str, float]:
        """Return (signal, confidence) for the most recent candle.

        Auto-retrains every ``retrain_every`` calls.
        """
        self._bars_since_train += 1
        should_retrain = (
            self._model is None
            or self._bars_since_train >= self._cfg.retrain_every
        )
        if should_retrain:
            self.fit(candles, labels or [0] * len(candles))

        if self._model is None:
            return ("HOLD", 0.0)

        features = self._kitchen.build(candles, labels)
        window = self._data_kitchen.split(features)
        if len(window.X_live) == 0:
            return ("HOLD", 0.0)

        try:
            pred = self._model.predict(window.X_live[-1:])
            pred_val = int(pred[0])
        except Exception:
            return ("HOLD", 0.0)

        try:
            proba = self._model.predict_proba(window.X_live[-1:])[0]
            confidence = float(np.max(proba))
        except (AttributeError, Exception):
            confidence = 1.0

        signal_map = {1: "BUY", -1: "SELL", 0: "HOLD"}
        return (signal_map.get(pred_val, "HOLD"), confidence)

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    @property
    def last_metrics(self) -> dict[str, float]:
        return dict(self._last_metrics)

    @property
    def feature_names(self) -> list[str]:
        return self._kitchen.feature_names

    def _build_model(self) -> Any:
        if self._custom_model is not None:
            return self._custom_model

        kind = self._cfg.model_kind
        params = dict(self._cfg.model_params)
        params.setdefault("random_state", self._cfg.random_state)

        try:
            from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
            from sklearn.linear_model import LogisticRegression

            if kind == "random_forest":
                params.setdefault("n_estimators", 100)
                return RandomForestClassifier(**params)
            if kind == "gradient_boost":
                params.setdefault("n_estimators", 100)
                return GradientBoostingClassifier(**params)
            if kind == "logistic":
                return LogisticRegression(**params)
        except ImportError:
            pass

        return _MajorityClassifier()

    def _save_model(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "model.pkl"
        with open(path, "wb") as f:
            pickle.dump(self._model, f)  # noqa: S301

    def load_model(self, directory: Path) -> None:
        path = directory / "model.pkl"
        if path.exists():
            with open(path, "rb") as f:
                self._model = pickle.load(f)  # noqa: S301 — trusted local artifact


class _MajorityClassifier:
    """No-sklearn fallback: always predicts the majority class from training."""

    def __init__(self) -> None:
        self._majority: int = 0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_MajorityClassifier":
        classes, counts = np.unique(y, return_counts=True)
        self._majority = int(classes[np.argmax(counts)]) if len(classes) > 0 else 0
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.full(len(X), self._majority)

    def score(self, X: np.ndarray, y: np.ndarray) -> float:
        preds = self.predict(X)
        return float((preds == y).mean()) if len(y) > 0 else 0.0
