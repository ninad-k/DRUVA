#!/usr/bin/env python3
"""CLI for walk-forward backtesting of the HMM regime-trader strategy.

Usage
-----
From the backend/ directory:

    python scripts/run_walk_forward.py \\
        --data data/nifty50_2020_2026.csv \\
        --train-window 252 \\
        --eval-window  126 \\
        --step         21  \\
        --output       results/walk_forward/ \\
        --inject-crashes

Alternatively, pull live data from yfinance:

    python scripts/run_walk_forward.py \\
        --ticker ^NSEI \\
        --years  6     \\
        --output results/walk_forward/

CSV format expected (if --data is used):
    date,open,high,low,close,volume
    2020-01-01,11900.05,12000.3,...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running from backend/ without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd


def _load_from_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"], index_col="date")
    df.columns = [c.lower() for c in df.columns]
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            raise ValueError(f"CSV missing column '{col}'")
    df.sort_index(inplace=True)
    df["volume"] = df["volume"].replace(0, 1).fillna(1)
    return df[["open", "high", "low", "close", "volume"]]


def _load_from_yfinance(ticker: str, years: int) -> pd.DataFrame:
    import yfinance as yf
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=years * 365 + 30)
    raw = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise RuntimeError(f"yfinance returned no data for {ticker}")
    if hasattr(raw.columns, "get_level_values"):
        raw.columns = raw.columns.get_level_values(0)
    df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df["volume"] = df["volume"].replace(0, 1).fillna(1)
    return df


def _print_summary(result) -> None:
    agg = result.aggregate
    print(f"\n{'='*60}")
    print(f"Walk-Forward Summary  ({agg['n_folds']} folds)")
    print(f"{'='*60}")
    for label, key in [("Strategy", "strategy"), ("Buy & Hold", "buy_and_hold")]:
        s = agg.get(key, {})
        print(f"\n  {label}:")
        for metric in ("sharpe", "total_return", "max_drawdown", "calmar"):
            if metric in s:
                mv = s[metric]
                print(f"    {metric:20s}  {mv['mean']:+.4f}  ± {mv['std']:.4f}")

    rd = agg.get("regime_detection", {})
    if rd.get("n_crash_events"):
        print(f"\n  Crash Detection ({rd['n_crash_events']} events):")
        print(f"    avg_latency_bars    {rd['avg_latency_bars']:.1f}")
        print(f"    detection_rate      {rd['detection_rate']:.2%}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest for DRUVA HMM regime-trader"
    )

    data_group = parser.add_mutually_exclusive_group(required=True)
    data_group.add_argument("--data", type=Path, help="Path to OHLCV CSV file")
    data_group.add_argument("--ticker", type=str, help="yfinance ticker (e.g. ^NSEI)")

    parser.add_argument(
        "--years", type=int, default=6,
        help="Years of history to download when --ticker is used (default: 6)",
    )
    parser.add_argument("--train-window", type=int, default=252)
    parser.add_argument("--eval-window", type=int, default=126)
    parser.add_argument("--step", type=int, default=21)
    parser.add_argument(
        "--output", type=Path, default=Path("results/walk_forward"),
        help="Output directory for CSVs and JSON",
    )
    parser.add_argument(
        "--inject-crashes", action="store_true",
        help="Inject synthetic 10-15%% crashes into each eval window",
    )
    parser.add_argument(
        "--n-crashes", type=int, default=2,
        help="Number of crashes to inject per fold (default: 2)",
    )
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    # Load data
    print("Loading data...")
    if args.data:
        ohlcv = _load_from_csv(args.data)
        print(f"  Loaded {len(ohlcv)} rows from {args.data}")
    else:
        ohlcv = _load_from_yfinance(args.ticker, args.years)
        print(f"  Downloaded {len(ohlcv)} rows for {args.ticker}")

    # Build config
    from app.strategies.ml.regime_trader.backtester import (
        WalkForwardBacktester,
        WalkForwardConfig,
    )

    config = WalkForwardConfig(
        train_window=args.train_window,
        eval_window=args.eval_window,
        step=args.step,
        inject_crashes=args.inject_crashes,
        n_crashes_per_fold=args.n_crashes,
        seed=args.seed,
    )

    print(
        f"Running walk-forward: train={config.train_window}, "
        f"eval={config.eval_window}, step={config.step}"
    )
    backtester = WalkForwardBacktester(config=config)
    result = backtester.run(ohlcv)

    # Print and save
    _print_summary(result)
    out_path = result.save(args.output)
    print(f"Results saved to: {out_path.resolve()}")
    print(f"  fold_metrics.csv")
    print(f"  aggregate.json")
    print(f"  walk_forward_detail.json")


if __name__ == "__main__":
    main()
