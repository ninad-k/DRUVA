"""FreqAIStrategy — Phase L.

Adapts ``FreqAIPipeline`` to the DRUVA ``Strategy`` contract.

The strategy is config-gated by ``DHRUVA_FREQAI_ENABLED``.  When disabled
it falls back to a neutral hold, enabling the HMM strategy to take over.

The label generation heuristic uses a simple forward-return threshold:
  next_return > threshold  → BUY (1)
  next_return < -threshold → SELL (-1)
  else                     → HOLD (0)

Operators can override ``generate_labels()`` in a subclass for custom targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.ml.freq_ai.pipeline import FreqAIPipeline, PipelineConfig


@dataclass
class FreqAIStrategy(Strategy):
    """ML strategy backed by ``FreqAIPipeline``.

    Parameters (set via ``self.parameters`` dict):
      ``retrain_every``   int   How often (bars) to retrain.  Default 100.
      ``label_threshold`` float Forward-return threshold for label gen.  Default 0.001.
      ``model_kind``      str   ``"random_forest"`` | ``"gradient_boost"`` | ``"logistic"``.
      ``enabled``         bool  When False, always emits neutral signal.  Default True.
    """

    _pipeline: FreqAIPipeline = field(init=False, repr=False)
    _candle_buffer: list[dict[str, float]] = field(default_factory=list, init=False)
    _label_buffer: list[int] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        params = self.parameters or {}
        cfg = PipelineConfig(
            model_kind=params.get("model_kind", "random_forest"),
            retrain_every=int(params.get("retrain_every", 100)),
            train_ratio=float(params.get("train_ratio", 0.80)),
            test_ratio=float(params.get("test_ratio", 0.10)),
        )
        self._pipeline = FreqAIPipeline(config=cfg)
        self._candle_buffer = []
        self._label_buffer = []
        self._label_threshold = float(params.get("label_threshold", 0.001))
        self._enabled = bool(params.get("enabled", True))

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:
        if not self._enabled:
            return None

        self._candle_buffer.append({
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
            "ts": candle.ts.isoformat(),
        })

        # Regenerate labels from the buffer's forward returns
        self._label_buffer = self._generate_labels(
            [c["close"] for c in self._candle_buffer],
            threshold=self._label_threshold,
        )

        signal_str, confidence = self._pipeline.predict(
            self._candle_buffer,
            labels=self._label_buffer,
        )

        if signal_str == "HOLD" or confidence < 0.5:
            return None

        side = "BUY" if signal_str == "BUY" else "SELL"
        return Signal(
            symbol=candle.symbol,
            side=side,
            quantity=self.default_quantity,
            confidence=confidence,
            reason=f"FreqAI:{self._pipeline.last_metrics.get('test_accuracy', 0):.2f}",
        )

    @staticmethod
    def _generate_labels(closes: list[float], threshold: float = 0.001) -> list[int]:
        """Label bars using next-bar forward return."""
        n = len(closes)
        labels = [0] * n
        for i in range(n - 1):
            if closes[i] == 0:
                continue
            fwd = (closes[i + 1] - closes[i]) / closes[i]
            if fwd > threshold:
                labels[i] = 1
            elif fwd < -threshold:
                labels[i] = -1
        return labels

    @property
    def default_quantity(self) -> Decimal:
        return Decimal(str(self.parameters.get("quantity", "1")))
