"""XGBoost signal model — feature engineering, training, and artifact save.

Usage
-----
# From CSV (offline):
python -m app.strategies.ml.training.train_xgboost --csv path/to/candles.csv

# From DB (online):
python -m app.strategies.ml.training.train_xgboost --symbol RELIANCE --exchange NSE --interval 1d --lookback-days 730
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from app.strategies.base import Candle

# Default artifact path — sits next to this package's ``models/`` directory.
_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_DEFAULT_OUTPUT = _MODELS_DIR / "xgboost_signal.pkl"


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _to_series(candles: list[Candle]) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Unpack Candle list into (open, high, low, close, volume) float Series."""
    opens   = pd.Series([float(c.open)   for c in candles], dtype=float)
    highs   = pd.Series([float(c.high)   for c in candles], dtype=float)
    lows    = pd.Series([float(c.low)    for c in candles], dtype=float)
    closes  = pd.Series([float(c.close)  for c in candles], dtype=float)
    volumes = pd.Series([float(c.volume) for c in candles], dtype=float)
    return opens, highs, lows, closes, volumes


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema12  = close.ewm(span=12, adjust=False).mean()
    ema26  = close.ewm(span=26, adjust=False).mean()
    line   = ema12 - ema26
    signal = line.ewm(span=9, adjust=False).mean()
    hist   = line - signal
    return line, signal, hist


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def _bollinger(close: pd.Series, period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
    ma     = close.rolling(period).mean()
    std    = close.rolling(period).std()
    upper  = ma + 2 * std
    lower  = ma - 2 * std
    return ma, upper, lower


def _adx_proxy(close: pd.Series, period: int = 14) -> pd.Series:
    """Simplified ADX proxy: rolling std of daily returns, normalised to [0, 100]."""
    ret   = close.pct_change()
    vol   = ret.rolling(period).std()
    # Scale so typical equity vol (~1-2 % daily std) maps to ~20-50 range.
    return (vol * 1000).clip(0, 100)


def build_feature_matrix(candles: list[Candle]) -> pd.DataFrame:
    """Return a DataFrame of engineered features (rows = candles)."""
    opens, highs, lows, closes, volumes = _to_series(candles)

    ret1  = closes.pct_change(1)
    ret5  = closes.pct_change(5)
    ret10 = closes.pct_change(10)

    rsi14         = _rsi(closes, 14)
    macd_line, macd_signal, macd_hist = _macd(closes)
    atr14         = _atr(highs, lows, closes, 14)
    vol_ratio     = volumes / volumes.rolling(20).mean()
    _, bb_upper, bb_lower = _bollinger(closes, 20)
    bb_band_range = (bb_upper - bb_lower).replace(0, float("nan"))
    bb_position   = (closes - bb_lower) / bb_band_range
    adx_proxy     = _adx_proxy(closes, 14)

    df = pd.DataFrame(
        {
            "ret_1":         ret1,
            "ret_5":         ret5,
            "ret_10":        ret10,
            "rsi_14":        rsi14,
            "macd_line":     macd_line,
            "macd_signal":   macd_signal,
            "macd_hist":     macd_hist,
            "atr_14":        atr14,
            "vol_ratio":     vol_ratio,
            "bb_position":   bb_position,
            "adx_proxy":     adx_proxy,
        }
    )
    return df


# ---------------------------------------------------------------------------
# Core training function
# ---------------------------------------------------------------------------

def train_from_candles(
    candles: list[Candle],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Feature-engineer, train, evaluate, and persist an XGBClassifier.

    Parameters
    ----------
    candles:
        Chronologically ordered list of :class:`~app.strategies.base.Candle` objects.
    output_path:
        Where to save the ``{"model": ..., "scaler": ...}`` joblib artifact.
        Defaults to ``models/xgboost_signal.pkl`` relative to this package.

    Returns
    -------
    dict with keys: ``precision``, ``recall``, ``f1``, ``roc_auc``,
    ``train_size``, ``test_size``, ``output_path``.
    """
    if output_path is None:
        output_path = _DEFAULT_OUTPUT

    if len(candles) < 100:
        raise ValueError(f"Need at least 100 candles; got {len(candles)}")

    # --- Feature matrix ---------------------------------------------------
    X_df = build_feature_matrix(candles)

    # --- Binary target: 1 if 5-day forward return > 2% -------------------
    closes = pd.Series([float(c.close) for c in candles], dtype=float)
    fwd_ret = closes.shift(-5) / closes - 1
    y = (fwd_ret > 0.02).astype(int)

    # Align and drop NaN rows (leading warmup + trailing 5 rows for target)
    combined = pd.concat([X_df, y.rename("target")], axis=1)
    combined.dropna(inplace=True)

    if len(combined) < 50:
        raise ValueError(
            f"After dropping NaN only {len(combined)} rows remain; need >=50."
        )

    X = combined.drop(columns=["target"]).values.astype(np.float32)
    y_arr = combined["target"].values.astype(np.int32)

    # --- Chronological train/test split (80/20) ---------------------------
    split = int(len(X) * 0.80)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y_arr[:split], y_arr[split:]

    # --- Scaling ----------------------------------------------------------
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    # --- Model ------------------------------------------------------------
    model = XGBClassifier(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        early_stopping_rounds=50,
        n_jobs=-1,
    )
    model.fit(
        X_train_s,
        y_train,
        eval_set=[(X_test_s, y_test)],
        verbose=False,
    )

    # --- Metrics ----------------------------------------------------------
    y_pred      = model.predict(X_test_s)
    y_prob      = model.predict_proba(X_test_s)[:, 1]
    precision   = float(precision_score(y_test, y_pred, zero_division=0))
    recall      = float(recall_score(y_test, y_pred, zero_division=0))
    f1          = float(f1_score(y_test, y_pred, zero_division=0))
    # roc_auc requires at least two classes in y_test
    try:
        roc_auc = float(roc_auc_score(y_test, y_prob))
    except ValueError:
        roc_auc = float("nan")

    print(f"[XGBoost] train={len(X_train)}  test={len(X_test)}")
    print(f"[XGBoost] precision={precision:.4f}  recall={recall:.4f}  "
          f"f1={f1:.4f}  roc_auc={roc_auc:.4f}")

    # --- Save artifact ----------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {"model": model, "scaler": scaler}
    joblib.dump(artifact, output_path)
    print(f"[XGBoost] artifact saved → {output_path}")

    return {
        "precision":   precision,
        "recall":      recall,
        "f1":          f1,
        "roc_auc":     roc_auc,
        "train_size":  len(X_train),
        "test_size":   len(X_test),
        "output_path": str(output_path),
    }


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def _load_candles_from_csv(csv_path: Path, symbol: str, exchange: str, interval: str) -> list[Candle]:
    """Load candles from a CSV with columns: ts,open,high,low,close,volume.

    The ``ts`` column is parsed as ISO-8601 or Unix timestamp (seconds).
    """
    candles: list[Candle] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_ts = row.get("ts") or row.get("datetime") or row.get("date", "")
            try:
                ts = datetime.fromisoformat(raw_ts)
            except ValueError:
                ts = datetime.fromtimestamp(float(raw_ts), tz=timezone.utc)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=ts,
                    open=Decimal(row.get("open", "0")),
                    high=Decimal(row.get("high", "0")),
                    low=Decimal(row.get("low", "0")),
                    close=Decimal(row.get("close", "0")),
                    volume=Decimal(row.get("volume", "0")),
                )
            )
    candles.sort(key=lambda c: c.ts)
    return candles


# ---------------------------------------------------------------------------
# DB loader (async → sync wrapper)
# ---------------------------------------------------------------------------

async def _load_candles_from_db(
    symbol: str,
    exchange: str,
    interval: str,
    lookback_days: int,
) -> list[Candle]:
    """Fetch candles from the TimescaleDB hypertable via OhlcvRepository."""
    # Import lazily — DB infra is not available in offline/CSV mode.
    from app.data.ohlcv_repository import OhlcvRepository
    from app.db.session import SessionLocal

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    async with SessionLocal() as session:
        repo = OhlcvRepository(session=session)
        candles = await repo.range(
            symbol=symbol,
            exchange=exchange,
            timeframe=interval,
            start=start,
            end=end,
        )
    return candles


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the DHRUVA XGBoost signal model."
    )
    parser.add_argument("--symbol",        default="NIFTY50",          help="Instrument symbol (default: NIFTY50)")
    parser.add_argument("--exchange",      default="NSE",               help="Exchange (default: NSE)")
    parser.add_argument("--interval",      default="1d",                help="Candle timeframe (default: 1d)")
    parser.add_argument("--lookback-days", default=730,   type=int,     help="Days of history to fetch from DB (default: 730)")
    parser.add_argument("--csv",           default=None,  type=Path,    help="Path to CSV file for offline training (skips DB)")
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        type=Path,
        help=f"Output path for the joblib artifact (default: {_DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if args.csv is not None:
        print(f"[XGBoost] Loading candles from CSV: {args.csv}")
        candles = _load_candles_from_csv(
            csv_path=args.csv,
            symbol=args.symbol,
            exchange=args.exchange,
            interval=args.interval,
        )
    else:
        print(
            f"[XGBoost] Loading candles from DB: symbol={args.symbol} "
            f"exchange={args.exchange} interval={args.interval} "
            f"lookback={args.lookback_days}d"
        )
        candles = asyncio.run(
            _load_candles_from_db(
                symbol=args.symbol,
                exchange=args.exchange,
                interval=args.interval,
                lookback_days=args.lookback_days,
            )
        )

    print(f"[XGBoost] Loaded {len(candles)} candles")
    metrics = train_from_candles(candles=candles, output_path=args.output)
    print("[XGBoost] Done.", metrics)
    sys.exit(0)


if __name__ == "__main__":
    main()
