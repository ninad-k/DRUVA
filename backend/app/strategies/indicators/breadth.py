"""Market breadth helpers — ATH ratios and sector rotation hints."""

from __future__ import annotations

from app.strategies.base import Candle


def is_at_ath(candles: list[Candle], lookback: int = 252, tolerance: float = 0.02) -> bool:
    """True if the latest close is within ``tolerance`` of the ``lookback`` high."""
    if not candles:
        return False
    window = candles[-lookback:] if len(candles) > lookback else candles
    highs = [float(c.high) for c in window]
    max_high = max(highs)
    last = float(candles[-1].close)
    if max_high <= 0:
        return False
    return last >= max_high * (1 - tolerance)


def breadth_score(at_ath: int, total: int) -> float:
    """0..1 — fraction of universe at/near ATH."""
    if total <= 0:
        return 0.0
    return at_ath / total
