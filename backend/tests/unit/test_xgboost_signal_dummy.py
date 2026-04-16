from __future__ import annotations

import numpy as np
import pytest

from app.strategies.ml.xgboost_signal import XGBoostSignalStrategy


@pytest.mark.unit
def test_xgboost_dummy_returns_hold_when_model_missing() -> None:
    strategy = XGBoostSignalStrategy(id="s1", account_id="a1")
    strategy._model = strategy.load_model("missing")
    prediction = strategy.predict(np.array([0.1, 0.2, 0.3, 0.4]))
    assert prediction.signal == "HOLD"
    assert prediction.probability == 0.0
