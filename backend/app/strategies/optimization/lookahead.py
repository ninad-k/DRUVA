"""Lookahead-bias detector — Phase F1.

Adapted from Freqtrade's ``lookahead-analysis`` (pattern only, not verbatim
code — GPL-3.0). Concept:

  Run the strategy over a *full* history and record the equity curve. Then
  run it again over a *truncated* history (say the first 70%). The signals
  generated on the overlap must be **identical**. If they differ, the
  strategy is peeking at future data — usually via `df.shift(-1)`, `iloc[-1]`
  on the wrong axis, or `pd.expanding()` without `min_periods`.

The detector returns a per-bar mismatch count plus the worst-divergence
window so the user can isolate the line that leaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)


SignalSeriesFn = Callable[[np.ndarray], np.ndarray]
"""``OHLCV (T x 5) → signal series (T,)`` — strategy under test."""


@dataclass(frozen=True)
class LookaheadReport:
    n_truncations: int
    mismatch_bars: int
    max_divergence_window: tuple[int, int] | None
    """``(start, end)`` of the worst contiguous mismatched stretch."""

    leak_score: float
    """Fraction of overlapping bars that disagree between full and truncated runs."""

    is_leaky: bool

    per_truncation: list[dict[str, float]]


def detect_lookahead_bias(
    *,
    ohlcv: np.ndarray,
    strategy: SignalSeriesFn,
    truncation_fractions: Sequence[float] = (0.7, 0.8, 0.9),
    leak_threshold: float = 0.001,
) -> LookaheadReport:
    """Re-run ``strategy`` over multiple history truncations and compare signals.

    Args:
        ohlcv: ``(T, 5)`` OHLCV array (oldest → newest).
        strategy: callable that returns a per-bar signal array.
        truncation_fractions: each fraction in [0, 1) is the length the
            strategy sees during that truncation pass. Default exercises
            70/80/90 % of history.
        leak_threshold: any mean divergence above this fraction flags
            ``is_leaky = True``. ``0.001 == 0.1%`` of bars allowed to differ
            for numeric jitter.
    """
    if ohlcv.ndim != 2 or ohlcv.shape[1] < 5:
        raise ValueError("ohlcv must be (T, 5) OHLCV")
    full_signals = np.asarray(strategy(ohlcv), dtype=float)
    if full_signals.shape[0] != ohlcv.shape[0]:
        raise ValueError("strategy must return one signal per OHLCV row")

    per_truncation: list[dict[str, float]] = []
    worst_mismatch_count = 0
    worst_window: tuple[int, int] | None = None
    total_mismatches = 0
    total_overlap = 0

    for frac in truncation_fractions:
        if not 0.0 < frac < 1.0:
            continue
        cut = max(2, int(ohlcv.shape[0] * frac))
        truncated_signals = np.asarray(strategy(ohlcv[:cut]), dtype=float)
        overlap = min(cut, truncated_signals.shape[0])
        if overlap < 2:
            continue
        full_slice = full_signals[:overlap]
        trunc_slice = truncated_signals[:overlap]
        mismatch_mask = ~_isclose(full_slice, trunc_slice)
        mismatches = int(mismatch_mask.sum())
        total_mismatches += mismatches
        total_overlap += overlap
        per_truncation.append(
            {
                "fraction": frac,
                "overlap_bars": float(overlap),
                "mismatch_bars": float(mismatches),
                "mismatch_pct": float(mismatches / overlap * 100.0),
            }
        )
        if mismatches > worst_mismatch_count:
            worst_mismatch_count = mismatches
            worst_window = _longest_true_run(mismatch_mask)

    leak_score = total_mismatches / total_overlap if total_overlap else 0.0
    is_leaky = leak_score > leak_threshold

    if is_leaky:
        logger.warning(
            "lookahead.leak_detected",
            leak_score=leak_score,
            worst_window=worst_window,
            total_mismatches=total_mismatches,
            total_overlap=total_overlap,
        )

    return LookaheadReport(
        n_truncations=len(per_truncation),
        mismatch_bars=total_mismatches,
        max_divergence_window=worst_window,
        leak_score=float(leak_score),
        is_leaky=is_leaky,
        per_truncation=per_truncation,
    )


def _isclose(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.isclose(a, b, equal_nan=True, atol=1e-9, rtol=1e-7)


def _longest_true_run(mask: np.ndarray) -> tuple[int, int] | None:
    if not mask.any():
        return None
    best_start = best_end = -1
    best_len = 0
    cur_start = None
    for i, v in enumerate(mask):
        if v:
            if cur_start is None:
                cur_start = i
            cur_len = i - cur_start + 1
            if cur_len > best_len:
                best_len = cur_len
                best_start, best_end = cur_start, i
        else:
            cur_start = None
    if best_start < 0:
        return None
    return best_start, best_end
