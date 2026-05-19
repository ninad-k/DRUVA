"""Performance metrics for walk-forward backtesting."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class BacktestMetrics:
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    n_trades: int = 0
    avg_regime_latency: float = float("nan")  # bars from crash to detection
    crash_detection_rates: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "sharpe": round(self.sharpe, 4),
            "sortino": round(self.sortino, 4),
            "calmar": round(self.calmar, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "win_rate": round(self.win_rate, 4),
            "n_trades": self.n_trades,
            "avg_regime_latency": round(self.avg_regime_latency, 2)
            if not np.isnan(self.avg_regime_latency)
            else None,
            "crash_detection_rates": [round(r, 4) for r in self.crash_detection_rates],
        }


def compute_metrics(
    equity_curve: pd.Series,
    trade_returns: list[float] | None = None,
    trading_days_per_year: int = 252,
    crash_injection_bars: list[int] | None = None,
    regime_labels: np.ndarray | None = None,
    crash_regime_idx: int = 0,
) -> BacktestMetrics:
    """Compute standard trading metrics from an equity curve.

    Args:
        equity_curve: Portfolio value indexed by date/integer bar.
        trade_returns: Optional list of per-trade returns (for win_rate).
        trading_days_per_year: Annualisation factor (252 for daily data).
        crash_injection_bars: Bar indices where crash was injected (for latency).
        regime_labels: HMM regime prediction array (same length as equity_curve).
        crash_regime_idx: Regime index that represents "Crash" (default 0).

    Returns:
        BacktestMetrics instance.
    """
    m = BacktestMetrics()
    if equity_curve is None or len(equity_curve) < 2:
        return m

    prices = np.array(equity_curve, dtype=float)
    daily_returns = np.diff(prices) / prices[:-1]

    # Total and annualised return
    m.total_return = float(prices[-1] / prices[0] - 1.0)
    n_bars = len(prices)
    years = n_bars / trading_days_per_year
    m.annualized_return = float((1 + m.total_return) ** (1 / max(years, 1e-6)) - 1)

    # Max drawdown
    rolling_max = np.maximum.accumulate(prices)
    drawdowns = (prices - rolling_max) / rolling_max
    m.max_drawdown = float(drawdowns.min())

    # Sharpe (daily, annualised)
    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std(ddof=1)
    m.sharpe = float(mean_ret / std_ret * np.sqrt(trading_days_per_year)) if std_ret > 0 else 0.0

    # Sortino (downside deviation only)
    neg_returns = daily_returns[daily_returns < 0]
    downside_std = neg_returns.std(ddof=1) if len(neg_returns) > 1 else 0.0
    m.sortino = float(mean_ret / downside_std * np.sqrt(trading_days_per_year)) if downside_std > 0 else 0.0

    # Calmar
    m.calmar = float(m.annualized_return / abs(m.max_drawdown)) if m.max_drawdown < 0 else 0.0

    # Win rate from trade returns
    if trade_returns:
        m.n_trades = len(trade_returns)
        wins = sum(1 for r in trade_returns if r > 0)
        m.win_rate = wins / m.n_trades if m.n_trades > 0 else 0.0

    # Regime latency: bars from crash injection to first Crash label
    if crash_injection_bars and regime_labels is not None and len(regime_labels) > 0:
        latencies = []
        detection_rates = []
        for inject_bar in crash_injection_bars:
            if inject_bar >= len(regime_labels):
                continue
            detected = False
            for offset in range(min(30, len(regime_labels) - inject_bar)):
                if regime_labels[inject_bar + offset] == crash_regime_idx:
                    latencies.append(float(offset))
                    detected = True
                    break
            detection_rates.append(1.0 if detected else 0.0)
        m.avg_regime_latency = float(np.mean(latencies)) if latencies else float("nan")
        m.crash_detection_rates = detection_rates

    return m


def compute_benchmark_bah(ohlcv: pd.DataFrame) -> pd.Series:
    """Buy-and-hold equity curve (1 unit bought at bar 0)."""
    prices = ohlcv["close"].values.astype(float)
    return pd.Series(prices / prices[0], index=ohlcv.index)


def compute_benchmark_sma200(ohlcv: pd.DataFrame) -> pd.Series:
    """SMA-200 crossover: long when close > SMA(200), else cash."""
    close = ohlcv["close"].astype(float)
    sma = close.rolling(200, min_periods=1).mean()
    position = (close > sma).astype(float)  # 1 = long, 0 = cash
    daily_ret = close.pct_change().fillna(0.0)
    strategy_ret = position.shift(1).fillna(0.0) * daily_ret
    return (1 + strategy_ret).cumprod()


def compute_benchmark_random(ohlcv: pd.DataFrame, seed: int = 42) -> pd.Series:
    """Random entry: randomly long or flat each bar."""
    rng = np.random.default_rng(seed)
    position = rng.choice([0.0, 1.0], size=len(ohlcv))
    close = ohlcv["close"].astype(float)
    daily_ret = close.pct_change().fillna(0.0).values
    strategy_ret = np.roll(position, 1) * daily_ret
    strategy_ret[0] = 0.0
    return pd.Series((1 + strategy_ret).cumprod(), index=ohlcv.index)
