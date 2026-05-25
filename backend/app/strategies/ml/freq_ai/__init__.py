"""FreqAI-style adaptive ML pipeline — Phase L.

Provides an adaptive ML pipeline that retrains on a rolling window of live
data and runs alongside (or instead of) the HMM regime detector, gated by
``DHRUVA_FREQAI_ENABLED`` in settings.

Core classes:
  ``FeatureKitchen``   — builds normalised feature matrices from OHLCV candles
  ``DataKitchen``      — splits data into train/test/live windows
  ``ModelAdapter``     — thin wrapper around sklearn-compatible models
  ``FreqAIPipeline``   — orchestrates training + prediction
  ``FreqAIStrategy``   — plugs FreqAIPipeline into the Strategy contract
"""

from app.strategies.ml.freq_ai.kitchen import DataKitchen, FeatureKitchen
from app.strategies.ml.freq_ai.pipeline import FreqAIPipeline, PipelineConfig
from app.strategies.ml.freq_ai.strategy import FreqAIStrategy

__all__ = [
    "DataKitchen",
    "FeatureKitchen",
    "FreqAIPipeline",
    "FreqAIStrategy",
    "PipelineConfig",
]
