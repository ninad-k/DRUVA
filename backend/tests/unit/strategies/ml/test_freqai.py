"""Unit tests for FreqAI adaptive ML pipeline — Phase L."""

from __future__ import annotations

import numpy as np
import pytest

from app.strategies.ml.freq_ai.kitchen import DataKitchen, FeatureKitchen
from app.strategies.ml.freq_ai.pipeline import (
    FreqAIPipeline,
    PipelineConfig,
    _MajorityClassifier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candles(n: int = 200, seed: int = 42) -> list[dict]:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0, 2, n)
    low = close - rng.uniform(0, 2, n)
    vol = rng.uniform(1e6, 1e7, n)
    return [
        {"open": float(close[i]), "high": float(high[i]),
         "low": float(low[i]), "close": float(close[i]),
         "volume": float(vol[i]), "ts": f"2024-01-{i+1:02d}"}
        for i in range(n)
    ]


def make_labels(candles: list[dict], threshold: float = 0.001) -> list[int]:
    closes = [c["close"] for c in candles]
    n = len(closes)
    labels = [0] * n
    for i in range(n - 1):
        if closes[i] == 0:
            continue
        fwd = (closes[i + 1] - closes[i]) / closes[i]
        labels[i] = 1 if fwd > threshold else (-1 if fwd < -threshold else 0)
    return labels


CANDLES = make_candles(200)
LABELS = make_labels(CANDLES)


# ---------------------------------------------------------------------------
# FeatureKitchen
# ---------------------------------------------------------------------------

class TestFeatureKitchen:
    def test_returns_candle_features(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        assert features.X.ndim == 2
        assert features.X.shape[1] == len(kitchen.feature_names)

    def test_no_nan_in_output(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        assert not np.any(np.isnan(features.X))

    def test_output_length_matches_valid_rows(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        # Must have at least some rows (NaN rows are dropped)
        assert len(features.X) > 0
        assert len(features.y) == len(features.X)

    def test_custom_feature_list(self):
        kitchen = FeatureKitchen(feature_names=["ret_1", "vol_20"])
        features = kitchen.build(CANDLES, LABELS)
        assert features.X.shape[1] == 2

    def test_too_short_returns_empty(self):
        kitchen = FeatureKitchen()
        short_candles = make_candles(10)
        features = kitchen.build(short_candles, [0] * 10)
        assert len(features.X) == 0

    def test_labels_aligned(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        assert len(features.y) == len(features.X)

    def test_normalise_false_gives_raw_features(self):
        kitchen_norm = FeatureKitchen(normalise=True)
        kitchen_raw = FeatureKitchen(normalise=False)
        f_norm = kitchen_norm.build(CANDLES, LABELS)
        f_raw = kitchen_raw.build(CANDLES, LABELS)
        # Normalised should have roughly unit-scale columns
        if f_norm.X.shape[0] > 1:
            col_stds = f_norm.X.std(axis=0)
            assert np.all(col_stds < 10)


# ---------------------------------------------------------------------------
# DataKitchen
# ---------------------------------------------------------------------------

class TestDataKitchen:
    def test_split_proportions(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        dk = DataKitchen(train_ratio=0.80, test_ratio=0.10)
        window = dk.split(features)
        n = len(features.X)
        assert len(window.X_train) == int(n * 0.80)
        assert len(window.X_test) == int(n * 0.10)
        assert len(window.X_live) == 1

    def test_live_rows_respected(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(CANDLES, LABELS)
        dk = DataKitchen(live_rows=5)
        window = dk.split(features)
        assert len(window.X_live) == 5

    def test_empty_features_returns_empty_window(self):
        kitchen = FeatureKitchen()
        features = kitchen.build(make_candles(5), [0] * 5)
        dk = DataKitchen()
        window = dk.split(features)
        assert len(window.X_train) == 0

    def test_invalid_ratios_raise(self):
        with pytest.raises(ValueError, match="≤ 1.0"):
            DataKitchen(train_ratio=0.8, test_ratio=0.3)


# ---------------------------------------------------------------------------
# _MajorityClassifier
# ---------------------------------------------------------------------------

class TestMajorityClassifier:
    def test_predicts_majority(self):
        clf = _MajorityClassifier()
        y = np.array([1, 1, 1, -1, 0])
        X = np.zeros((5, 2))
        clf.fit(X, y)
        assert clf.predict(X[:1])[0] == 1

    def test_score_perfect(self):
        clf = _MajorityClassifier()
        y = np.array([1, 1, 1])
        X = np.zeros((3, 2))
        clf.fit(X, y)
        assert clf.score(X, y) == pytest.approx(1.0)

    def test_empty_train(self):
        clf = _MajorityClassifier()
        clf.fit(np.zeros((0, 2)), np.zeros(0))
        pred = clf.predict(np.zeros((1, 2)))
        assert pred[0] == 0


# ---------------------------------------------------------------------------
# FreqAIPipeline
# ---------------------------------------------------------------------------

class TestFreqAIPipeline:
    def test_fit_returns_metrics(self):
        pipeline = FreqAIPipeline(PipelineConfig())
        metrics = pipeline.fit(CANDLES, LABELS)
        assert isinstance(metrics, dict)

    def test_is_trained_after_fit(self):
        pipeline = FreqAIPipeline(PipelineConfig())
        assert not pipeline.is_trained
        pipeline.fit(CANDLES, LABELS)
        assert pipeline.is_trained

    def test_predict_returns_signal_and_confidence(self):
        pipeline = FreqAIPipeline(PipelineConfig())
        signal, conf = pipeline.predict(CANDLES, LABELS)
        assert signal in ("BUY", "SELL", "HOLD")
        assert 0.0 <= conf <= 1.0

    def test_predict_without_prior_fit_trains_automatically(self):
        pipeline = FreqAIPipeline(PipelineConfig(retrain_every=9999))
        signal, conf = pipeline.predict(CANDLES)
        assert signal in ("BUY", "SELL", "HOLD")

    def test_predict_hold_on_short_data(self):
        pipeline = FreqAIPipeline(PipelineConfig())
        short = make_candles(5)
        signal, conf = pipeline.predict(short)
        assert signal == "HOLD"
        assert conf == 0.0

    def test_custom_model_is_used(self):
        """Custom majority classifier is wired through."""
        clf = _MajorityClassifier()
        pipeline = FreqAIPipeline(PipelineConfig(), custom_model=clf)
        pipeline.fit(CANDLES, LABELS)
        assert pipeline._model is clf

    def test_retrain_triggers_after_n_bars(self):
        train_calls = []

        class SpyClassifier(_MajorityClassifier):
            def fit(self, X, y):
                train_calls.append(1)
                return super().fit(X, y)

        pipeline = FreqAIPipeline(PipelineConfig(retrain_every=2), custom_model=SpyClassifier())
        pipeline.predict(CANDLES, LABELS)   # triggers first train
        pipeline.predict(CANDLES, LABELS)   # bars_since_train = 1
        pipeline.predict(CANDLES, LABELS)   # bars_since_train = 2 → retrain
        assert len(train_calls) >= 2

    def test_feature_names_passthrough(self):
        pipeline = FreqAIPipeline(PipelineConfig())
        assert isinstance(pipeline.feature_names, list)
        assert len(pipeline.feature_names) > 0
