"""Walk-forward backtester for the HMM regime-trader strategy.

Rolling train/eval design:
  - Train window  : 252 bars (≈1 trading year)
  - Eval window   : 126 bars (≈6 months)
  - Step          : 21 bars (≈1 month)

Each fold:
  1. Fit RegimeDetector on train window.
  2. Predict regimes on eval window (forward-only, no look-ahead).
  3. Simulate a simple regime-filtered long-only strategy on NIFTY 50.
  4. Compare against Buy-and-Hold, SMA-200, and Random-Entry benchmarks.
  5. Optionally inject crashes into the eval window and measure detection latency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.strategies.ml.regime_trader.hmm_engine import RegimeDetector
from app.strategies.ml.regime_trader.backtester.crash_injector import CrashInjector
from app.strategies.ml.regime_trader.backtester.metrics import (
    BacktestMetrics,
    compute_metrics,
    compute_benchmark_bah,
    compute_benchmark_sma200,
    compute_benchmark_random,
)


@dataclass
class WalkForwardConfig:
    train_window: int = 252
    eval_window: int = 126
    step: int = 21
    inject_crashes: bool = False
    n_crashes_per_fold: int = 2
    crash_drop_range: tuple[float, float] = (0.10, 0.15)
    seed: int = 42
    # Regime indices
    bull_regime: int = 3       # long-only entry
    euphoria_regime: int = 4   # also long
    neutral_regime: int = 2    # stay flat / close if already long
    bear_regime: int = 1       # short or flat
    crash_regime: int = 0      # flat / forced exit


@dataclass
class FoldResult:
    fold_index: int
    train_start: Any
    train_end: Any
    eval_start: Any
    eval_end: Any
    strategy_metrics: BacktestMetrics
    bah_metrics: BacktestMetrics
    sma200_metrics: BacktestMetrics
    random_metrics: BacktestMetrics
    regime_distribution: dict[str, float]  # regime_name → fraction of eval bars
    equity_curve: list[float] = field(default_factory=list)
    crash_injection_bars: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "fold": self.fold_index,
            "train_start": str(self.train_start),
            "train_end": str(self.train_end),
            "eval_start": str(self.eval_start),
            "eval_end": str(self.eval_end),
            "strategy": self.strategy_metrics.to_dict(),
            "benchmarks": {
                "buy_and_hold": self.bah_metrics.to_dict(),
                "sma_200": self.sma200_metrics.to_dict(),
                "random_entry": self.random_metrics.to_dict(),
            },
            "regime_distribution": self.regime_distribution,
            "crash_injection_bars": self.crash_injection_bars,
            "equity_curve": [round(v, 4) for v in self.equity_curve],
        }


@dataclass
class WalkForwardResult:
    config: WalkForwardConfig
    folds: list[FoldResult] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def compute_aggregate(self) -> None:
        """Fill `aggregate` with mean/std across folds."""
        if not self.folds:
            return

        def _mean_std(values: list[float]) -> dict[str, float]:
            arr = np.array(values)
            return {"mean": float(arr.mean()), "std": float(arr.std(ddof=1))}

        keys = ["sharpe", "sortino", "max_drawdown", "total_return", "calmar", "win_rate"]
        strategy_vals: dict[str, list[float]] = {k: [] for k in keys}
        bah_vals: dict[str, list[float]] = {k: [] for k in keys}

        latencies: list[float] = []
        detection_rates: list[float] = []

        for fold in self.folds:
            for k in keys:
                strategy_vals[k].append(getattr(fold.strategy_metrics, k))
                bah_vals[k].append(getattr(fold.bah_metrics, k))
            lat = fold.strategy_metrics.avg_regime_latency
            if not np.isnan(lat):
                latencies.append(lat)
            detection_rates.extend(fold.strategy_metrics.crash_detection_rates)

        self.aggregate = {
            "n_folds": len(self.folds),
            "strategy": {k: _mean_std(v) for k, v in strategy_vals.items()},
            "buy_and_hold": {k: _mean_std(v) for k, v in bah_vals.items()},
            "regime_detection": {
                "avg_latency_bars": round(np.mean(latencies), 2) if latencies else None,
                "detection_rate": round(np.mean(detection_rates), 4) if detection_rates else None,
                "n_crash_events": len(detection_rates),
            },
        }

    def save(self, output_dir: str | Path) -> Path:
        """Write per-fold CSV + aggregate JSON to output_dir."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Fold-level CSV
        rows = []
        for f in self.folds:
            row = {
                "fold": f.fold_index,
                "eval_start": f.eval_start,
                "eval_end": f.eval_end,
                **{f"strategy_{k}": v for k, v in f.strategy_metrics.to_dict().items()
                   if not isinstance(v, list)},
                **{f"bah_{k}": v for k, v in f.bah_metrics.to_dict().items()
                   if not isinstance(v, list)},
            }
            rows.append(row)
        pd.DataFrame(rows).to_csv(out / "fold_metrics.csv", index=False)

        # Aggregate JSON
        with open(out / "aggregate.json", "w") as fh:
            json.dump(self.aggregate, fh, indent=2, default=str)

        # Full detail JSON
        detail = {
            "config": {
                "train_window": self.config.train_window,
                "eval_window": self.config.eval_window,
                "step": self.config.step,
                "inject_crashes": self.config.inject_crashes,
            },
            "folds": [f.to_dict() for f in self.folds],
            "aggregate": self.aggregate,
        }
        with open(out / "walk_forward_detail.json", "w") as fh:
            json.dump(detail, fh, indent=2, default=str)

        return out


# ---------------------------------------------------------------------------
# Strategy simulation
# ---------------------------------------------------------------------------

def _simulate_regime_strategy(
    ohlcv: pd.DataFrame,
    regimes: np.ndarray,
    config: WalkForwardConfig,
) -> tuple[pd.Series, list[float]]:
    """Simulate a regime-filtered long-only strategy.

    Rules:
    - Enter long on Bull or Euphoria regime.
    - Exit to cash on Neutral.
    - Short (or just flat) on Bear/Crash.

    Returns:
        (equity_curve, trade_returns)
    """
    close = ohlcv["close"].values.astype(float)
    n = len(close)
    equity = np.ones(n)
    trade_returns: list[float] = []

    position = 0.0  # 0 = flat, 1 = long, -0.5 = short
    entry_price = 0.0

    for i in range(1, n):
        regime = int(regimes[i - 1])  # use yesterday's regime (no look-ahead)
        prev_position = position

        if regime in (config.bull_regime, config.euphoria_regime):
            position = 1.0
        elif regime == config.neutral_regime:
            position = 0.0
        else:  # Bear or Crash
            position = 0.0  # flat; change to -0.5 to enable short

        # Bar return
        bar_ret = (close[i] - close[i - 1]) / close[i - 1]
        equity[i] = equity[i - 1] * (1.0 + prev_position * bar_ret)

        # Track trade returns on position close
        if prev_position != 0.0 and position == 0.0 and entry_price > 0:
            trade_returns.append(close[i - 1] / entry_price - 1.0)
            entry_price = 0.0
        if prev_position == 0.0 and position != 0.0:
            entry_price = close[i]

    return pd.Series(equity, index=ohlcv.index), trade_returns


# ---------------------------------------------------------------------------
# Main backtester
# ---------------------------------------------------------------------------

class WalkForwardBacktester:
    """Rolls a train/eval window across a historical OHLCV series.

    Args:
        config: Walk-forward configuration.
    """

    REGIME_NAMES = ["Crash", "Bear", "Neutral", "Bull", "Euphoria"]

    def __init__(self, config: WalkForwardConfig | None = None) -> None:
        self.config = config or WalkForwardConfig()

    def run(self, ohlcv: pd.DataFrame) -> WalkForwardResult:
        """Execute the full walk-forward backtest.

        Args:
            ohlcv: DataFrame with ['open', 'high', 'low', 'close', 'volume'].
                   Must have at least train_window + eval_window rows.

        Returns:
            WalkForwardResult with per-fold results and aggregate statistics.
        """
        cfg = self.config
        n = len(ohlcv)
        min_rows = cfg.train_window + cfg.eval_window
        if n < min_rows:
            raise ValueError(
                f"OHLCV has {n} rows but walk-forward needs at least "
                f"{min_rows} (train={cfg.train_window} + eval={cfg.eval_window})."
            )

        result = WalkForwardResult(config=cfg)
        injector = CrashInjector(
            n_crashes=cfg.n_crashes_per_fold,
            drop_range=cfg.crash_drop_range,
            seed=cfg.seed,
        ) if cfg.inject_crashes else None

        fold_idx = 0
        start = 0
        rng_seed = cfg.seed  # per-fold seed offset

        while start + cfg.train_window + cfg.eval_window <= n:
            train_end = start + cfg.train_window
            eval_end = train_end + cfg.eval_window

            train_slice = ohlcv.iloc[start:train_end]
            eval_slice = ohlcv.iloc[train_end:eval_end].copy()

            # Optional crash injection into the eval window only
            injection_bars: list[int] = []
            if injector is not None:
                inj_result = CrashInjector(
                    n_crashes=cfg.n_crashes_per_fold,
                    drop_range=cfg.crash_drop_range,
                    seed=rng_seed + fold_idx,
                ).inject(eval_slice)
                eval_slice = inj_result.ohlcv
                injection_bars = inj_result.injection_bars

            # Train
            detector = RegimeDetector(n_regimes=5, random_state=cfg.seed + fold_idx)
            try:
                detector.fit(train_slice)
            except Exception:  # noqa: BLE001
                start += cfg.step
                fold_idx += 1
                continue

            # Predict on eval (forward-only)
            try:
                regimes = detector.predict_forward(eval_slice)
            except Exception:  # noqa: BLE001
                start += cfg.step
                fold_idx += 1
                continue

            # Simulate strategy
            equity_curve, trade_returns = _simulate_regime_strategy(eval_slice, regimes, cfg)

            # Strategy metrics
            strategy_metrics = compute_metrics(
                equity_curve=equity_curve,
                trade_returns=trade_returns,
                crash_injection_bars=injection_bars,
                regime_labels=regimes,
                crash_regime_idx=cfg.crash_regime,
            )

            # Benchmark metrics
            bah_eq = compute_benchmark_bah(eval_slice)
            sma_eq = compute_benchmark_sma200(eval_slice)
            rnd_eq = compute_benchmark_random(eval_slice, seed=cfg.seed + fold_idx)

            bah_metrics = compute_metrics(bah_eq)
            sma_metrics = compute_metrics(sma_eq)
            rnd_metrics = compute_metrics(rnd_eq)

            # Regime distribution
            regime_dist = {}
            for i, name in enumerate(self.REGIME_NAMES):
                regime_dist[name] = float((regimes == i).mean())

            fold = FoldResult(
                fold_index=fold_idx,
                train_start=ohlcv.index[start],
                train_end=ohlcv.index[train_end - 1],
                eval_start=ohlcv.index[train_end],
                eval_end=ohlcv.index[eval_end - 1],
                strategy_metrics=strategy_metrics,
                bah_metrics=bah_metrics,
                sma200_metrics=sma_metrics,
                random_metrics=rnd_metrics,
                regime_distribution=regime_dist,
                equity_curve=list(equity_curve.values),
                crash_injection_bars=injection_bars,
            )
            result.folds.append(fold)

            start += cfg.step
            fold_idx += 1

        result.compute_aggregate()
        return result
