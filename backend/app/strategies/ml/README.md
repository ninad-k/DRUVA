# ML Strategies — Plugin Contract

This folder is the dedicated home for AI/ML trading strategies. It is designed so adding a new model does **not** require any changes outside `app/strategies/ml/`.

## Contract

Every ML strategy must:

1. **Subclass** `MLStrategy` from [`base_ml.py`](base_ml.py).
2. **Declare a `FeatureSpec`** — list of features, lookback window, transforms.
3. **Implement `load_model(version: str)`** — load from `models/{strategy_name}/{version}/`.
4. **Implement `predict(features: np.ndarray) -> Prediction`** — return `(signal_class, probability)`.
5. **Optionally implement `train(dataset)`** — used only by standalone training CLIs, never at runtime.
6. **Register** via `@register_strategy("my_ml_strategy_v1")` from `app.strategies.registry`.

## Folder layout

```
ml/
├── base_ml.py               Abstract MLStrategy + Prediction/FeatureSpec
├── features/                Feature engineering functions (pure, no side effects)
│   ├── price_features.py
│   ├── technical_features.py
│   └── builder.py
├── models/                  Serialized artifacts + registry
│   ├── registry.json
│   ├── lstm_predictor/v1/
│   └── xgboost_signal/v3/
├── lstm_predictor.py        PyTorch LSTM (next-bar direction)
├── xgboost_signal.py        XGBoost multi-class (BUY/SELL/HOLD)
├── rf_classifier.py         RandomForest baseline
├── training/                Offline training CLIs (never called at runtime)
└── reinforcement/           Optional RL agents (post-MVP1)
```

## Runtime rules

- **Load once, predict fast.** Models are cached via `functools.lru_cache` keyed on `(class, version)`.
- **Hard latency budget: < 20 ms per prediction** on commodity CPU. Anything heavier must run in a dedicated worker process.
- **Trace every prediction.** Wrap `predict()` in a span named `ml.predict` with attributes `model`, `version`, `signal`, `confidence`.
- **Count every prediction.** Increment `dhruva_ml_predictions_total{model,signal}`.
- **Model artifacts are not committed to git.** Store them in object storage or a mounted volume; reference them in `models/registry.json`.

## registry.json schema

```json
{
  "models": {
    "xgboost_signal": {
      "latest": "v3",
      "versions": {
        "v3": {
          "path": "models/xgboost_signal/v3/model.json",
          "trained_at": "2026-03-20T10:00:00Z",
          "features": ["ret_1", "ret_5", "rsi_14", "macd_hist"],
          "metrics": { "auc": 0.63, "acc": 0.57 }
        }
      }
    }
  }
}
```

## Adding a new model (checklist)

- [ ] Subclass `MLStrategy` in a new file (e.g., `my_new_model.py`).
- [ ] Declare `FeatureSpec`.
- [ ] Implement `load_model` and `predict`.
- [ ] Add training script under `training/` and document how to run it.
- [ ] Drop the trained artifact into `models/my_new_model/v1/`.
- [ ] Register an entry in `models/registry.json`.
- [ ] Call `@register_strategy("my_new_model_v1")` on the class.
- [ ] Write at least one unit test that mocks `load_model` and asserts `predict` returns the expected shape.
- [ ] Run a backtest and commit the result as a `Report` row for reference.
