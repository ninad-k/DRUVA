"""Pure-Python technical indicators used by the AI advisor.

No external deps — just stdlib. Inputs are sequences of closing prices
(oldest first). All functions are deterministic and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass


def ema(values: list[float], length: int) -> list[float]:
    if length <= 0 or not values:
        return []
    k = 2.0 / (length + 1)
    out: list[float] = []
    prev: float | None = None
    for v in values:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def roc(values: list[float], length: int) -> float | None:
    """Rate-of-change over ``length`` periods, in percent."""
    if len(values) <= length:
        return None
    past = values[-length - 1]
    if past == 0:
        return None
    return (values[-1] / past - 1.0) * 100.0


@dataclass(frozen=True)
class VCPResult:
    is_vcp: bool
    tightness: float     # 0..1 — closer to 1 = tighter
    contractions: int    # number of successively shallower pullbacks
    breakout: bool       # price broke above pivot high
    pivot_high: float


def detect_vcp(closes: list[float], window: int = 60) -> VCPResult:
    """Rough Mark Minervini-style VCP detector.

    We slide over the last ``window`` bars, find local swing highs/lows,
    measure pullback depths. A valid VCP has >=2 successively shallower
    pullbacks and tight price action in the final 5–10 bars.
    """
    if len(closes) < window:
        return VCPResult(False, 0.0, 0, False, 0.0)

    segment = closes[-window:]
    pivot_high = max(segment)

    pullbacks: list[float] = []
    peak = segment[0]
    trough = segment[0]
    for v in segment:
        if v > peak:
            if peak > trough:
                pullbacks.append((peak - trough) / peak * 100.0)
            peak = v
            trough = v
        elif v < trough:
            trough = v

    contractions = 0
    for i in range(1, len(pullbacks)):
        if pullbacks[i] < pullbacks[i - 1]:
            contractions += 1

    tail = segment[-7:]
    if not tail:
        return VCPResult(False, 0.0, contractions, False, pivot_high)
    tail_range_pct = (max(tail) - min(tail)) / max(tail) * 100.0 if max(tail) > 0 else 100.0
    tightness = max(0.0, min(1.0, 1.0 - tail_range_pct / 5.0))  # <=5% = 0..1

    breakout = segment[-1] >= pivot_high * 0.995
    is_vcp = contractions >= 1 and tightness >= 0.3 and len(pullbacks) >= 2
    return VCPResult(is_vcp=is_vcp, tightness=tightness, contractions=contractions,
                     breakout=breakout, pivot_high=pivot_high)


def ema_trend_score(closes: list[float]) -> float:
    """Score 0..100: price above rising 21/63 EMAs is strongest."""
    if len(closes) < 70:
        return 0.0
    e21 = ema(closes, 21)
    e63 = ema(closes, 63)
    price = closes[-1]
    score = 0.0
    if price > e21[-1]:
        score += 30.0
    if price > e63[-1]:
        score += 25.0
    if e21[-1] > e63[-1]:
        score += 20.0
    if e21[-1] > e21[-5]:
        score += 15.0
    if e63[-1] > e63[-20]:
        score += 10.0
    return min(100.0, score)
