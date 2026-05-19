"""Synthetic crash injection for regime-detector stress testing.

Randomly inserts 10-15% single-bar price drops into an OHLCV DataFrame so
the walk-forward harness can measure how quickly the HMM detects regime shifts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class InjectedCrash:
    bar_index: int
    date: object  # pd.Timestamp or int
    drop_pct: float  # e.g. 0.12 means 12% drop


@dataclass
class CrashInjectionResult:
    ohlcv: pd.DataFrame
    crashes: list[InjectedCrash] = field(default_factory=list)

    @property
    def injection_bars(self) -> list[int]:
        return [c.bar_index for c in self.crashes]


class CrashInjector:
    """Insert synthetic crash events into OHLCV data.

    After injection the prices are re-chained so all subsequent bars are
    consistently lower — this simulates a real gap-down opening rather than
    a single-bar spike that immediately recovers.

    Args:
        n_crashes: Number of crashes to inject.
        drop_range: (min_drop, max_drop) as fractions (e.g. 0.10 = 10%).
        min_gap: Minimum number of bars between crash injection points.
        seed: Random seed for reproducibility.
    """

    def __init__(
        self,
        n_crashes: int = 3,
        drop_range: tuple[float, float] = (0.10, 0.15),
        min_gap: int = 30,
        seed: int = 42,
    ) -> None:
        self.n_crashes = n_crashes
        self.drop_range = drop_range
        self.min_gap = min_gap
        self.rng = np.random.default_rng(seed)

    def inject(self, ohlcv: pd.DataFrame) -> CrashInjectionResult:
        """Return a copy of ohlcv with synthetic crashes injected.

        Crashes are placed in the second half of the series (after the initial
        warm-up period for indicators) so regime detection can be measured.

        Args:
            ohlcv: DataFrame with columns ['open', 'high', 'low', 'close', 'volume'].

        Returns:
            CrashInjectionResult with modified ohlcv and crash metadata.
        """
        df = ohlcv.copy()
        n = len(df)
        if n < 60:
            return CrashInjectionResult(ohlcv=df, crashes=[])

        # Eligible injection range: between 25% and 85% of the series
        lo = max(30, n // 4)
        hi = min(n - 10, int(n * 0.85))
        if hi - lo < self.n_crashes * self.min_gap:
            # Not enough room — inject fewer crashes
            n_crashes = max(1, (hi - lo) // self.min_gap)
        else:
            n_crashes = self.n_crashes

        # Pick injection points with minimum gap enforced
        injection_bars: list[int] = []
        attempts = 0
        while len(injection_bars) < n_crashes and attempts < 1000:
            candidate = int(self.rng.integers(lo, hi))
            if all(abs(candidate - b) >= self.min_gap for b in injection_bars):
                injection_bars.append(candidate)
            attempts += 1
        injection_bars.sort()

        crashes: list[InjectedCrash] = []
        close = df["close"].values.astype(float).copy()
        open_ = df["open"].values.astype(float).copy()
        high = df["high"].values.astype(float).copy()
        low = df["low"].values.astype(float).copy()

        for bar in injection_bars:
            drop = float(self.rng.uniform(*self.drop_range))
            multiplier = 1.0 - drop
            # Gap-down: all prices from bar onward shift down by the drop fraction
            # This preserves relative moves after the crash while reflecting the step-change.
            close[bar:] *= multiplier
            open_[bar:] *= multiplier
            high[bar:] *= multiplier
            low[bar:] *= multiplier
            # Make the crash bar look like a proper down-candle
            open_[bar] = close[bar - 1] if bar > 0 else open_[bar]
            high[bar] = open_[bar]
            low[bar] = close[bar]
            crashes.append(
                InjectedCrash(
                    bar_index=bar,
                    date=df.index[bar],
                    drop_pct=drop,
                )
            )

        df["close"] = close
        df["open"] = open_
        df["high"] = high
        df["low"] = low
        # Volume spike at crash bars (2-5x)
        for c in crashes:
            df.at[df.index[c.bar_index], "volume"] *= float(self.rng.uniform(2.0, 5.0))

        return CrashInjectionResult(ohlcv=df, crashes=crashes)
