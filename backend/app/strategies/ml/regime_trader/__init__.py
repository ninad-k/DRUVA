"""Regime-Trader: HMM-based volatility regime detection and dynamic allocation.

A production-grade volatility regime classifier using Hidden Markov Models (HMM).
Detects market regimes (Crash, Bear, Neutral, Bull, Euphoria) with:
- Forward algorithm inference (no look-ahead bias)
- Stability filter (3-bar persistence, flickering detection)
- Dynamic allocation based on regime and confidence
- Leverage control (1.25x in Bull regime, 1.0x elsewhere)
"""

from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector
from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy

__all__ = [
    "RegimeDetector",
    "RegimeTraderStrategy",
]
