"""Volatility Contraction Pattern (VCP) stage detection.

Based on Minervini-style VCP:

- Uptrend on a higher timeframe (21-EMA slope up, close above 21/50-EMA).
- 2+ consecutive consolidation bases, each shallower than the prior one.
- Volume dry-up: 20-day avg volume inside the latest base is < 0.6× the
  prior base's average volume.

Stages (0 based on Stan Weinstein ideology, adapted):

- stage_1 — base forming, volatility contracting, still early.
- stage_2 — established uptrend, multiple contractions, constructive.
- stage_3 — tight final base right under pivot, ready for breakout.
- stage_4 — breakout in progress.
- stage_5 — extended / distribution.
- stage_6 — breakdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.strategies.base import Candle


@dataclass(frozen=True)
class VcpAssessment:
    stage: str  # "stage_1" .. "stage_6"
    score: float  # 0.0 .. 1.0
    bases: int
    contraction_ratios: list[float] = field(default_factory=list)
    volume_dryup_ratio: float = 0.0
    ema21: float = 0.0
    pivot: float | None = None
    breakout: bool = False


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    k = 2.0 / (period + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def _detect_bases(highs: list[float], lows: list[float], window: int = 10) -> list[tuple[int, int, float]]:
    """Naive base detection.

    Walk the series right-to-left; whenever the latest ``window`` bars stay
    within a tight range (max-min < 15% of the range midpoint) treat that
    window as a base. Returns list of (start_idx, end_idx, depth_pct).
    """
    bases: list[tuple[int, int, float]] = []
    n = len(highs)
    i = n - 1
    while i - window >= 0:
        win_high = max(highs[i - window + 1 : i + 1])
        win_low = min(lows[i - window + 1 : i + 1])
        mid = (win_high + win_low) / 2.0 if (win_high + win_low) > 0 else 1.0
        depth = (win_high - win_low) / mid if mid > 0 else 1.0
        if depth < 0.15:
            bases.append((i - window + 1, i, depth * 100))
            i -= window
        else:
            i -= 1
    return list(reversed(bases))


def detect_vcp(
    candles: list[Candle],
    *,
    min_bases: int = 2,
    contraction_cap: float = 0.6,
    volume_dryup_cap: float = 0.6,
) -> VcpAssessment:
    if len(candles) < 60:
        return VcpAssessment(stage="stage_1", score=0.0, bases=0)

    closes = [float(c.close) for c in candles]
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    volumes = [float(c.volume) for c in candles]

    ema21 = _ema(closes, 21)[-1]
    ema50 = _ema(closes, 50)[-1] if len(closes) >= 50 else ema21
    last = closes[-1]

    uptrend = last >= ema21 >= ema50
    bases = _detect_bases(highs, lows, window=10)
    bases_count = len(bases)

    contraction_ratios: list[float] = []
    contracting = True
    for i in range(1, len(bases)):
        prev = bases[i - 1][2]
        cur = bases[i][2]
        if prev <= 0:
            continue
        ratio = cur / prev
        contraction_ratios.append(ratio)
        if ratio > contraction_cap:
            contracting = False

    volume_dryup_ratio = 0.0
    dry_volume_ok = False
    if bases_count >= 2:
        last_start, last_end, _ = bases[-1]
        prev_start, prev_end, _ = bases[-2]
        last_vol = sum(volumes[last_start : last_end + 1]) / max(last_end - last_start + 1, 1)
        prev_vol = sum(volumes[prev_start : prev_end + 1]) / max(prev_end - prev_start + 1, 1)
        if prev_vol > 0:
            volume_dryup_ratio = last_vol / prev_vol
            dry_volume_ok = volume_dryup_ratio < volume_dryup_cap

    pivot = None
    breakout = False
    if bases:
        _, end, _ = bases[-1]
        pivot = max(highs[max(0, end - 10) : end + 1])
        breakout = last > pivot * 1.005 if pivot else False

    # Score: combination of trend + contraction + dry-up.
    score = 0.0
    if uptrend:
        score += 0.3
    if bases_count >= min_bases:
        score += 0.25
    if contracting and contraction_ratios:
        score += 0.2
    if dry_volume_ok:
        score += 0.2
    # Small boost for extra bases beyond minimum
    score += min(0.05, max(0, bases_count - min_bases) * 0.02)

    # Stage classification
    if not uptrend:
        stage = "stage_6" if last < ema21 * 0.95 else "stage_1"
    elif breakout:
        stage = "stage_4"
    elif bases_count >= min_bases and contracting and dry_volume_ok:
        stage = "stage_3"
    elif bases_count >= 1:
        stage = "stage_2"
    else:
        stage = "stage_1"

    # Penalise extended: price too far above ema21 means it's already running.
    if ema21 > 0 and last / ema21 > 1.25:
        stage = "stage_5"
        score *= 0.5

    return VcpAssessment(
        stage=stage,
        score=max(0.0, min(1.0, score)),
        bases=bases_count,
        contraction_ratios=contraction_ratios,
        volume_dryup_ratio=volume_dryup_ratio,
        ema21=ema21,
        pivot=pivot,
        breakout=breakout,
    )


def trailing_ema_stop(candles: list[Candle], period: int = 21) -> Decimal | None:
    closes = [float(c.close) for c in candles]
    if len(closes) < period:
        return None
    ema = _ema(closes, period)[-1]
    return Decimal(f"{ema:.4f}")
