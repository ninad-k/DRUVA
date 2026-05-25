"""FeatureKitchen and DataKitchen — Phase L.

FeatureKitchen:
  Converts a list of OHLCV candles into a normalised feature matrix.
  The feature set is configurable but defaults to a rich set of price,
  volume, and momentum features that cover most systematic strategies.

  All features are computed on the raw series without look-ahead:
  each row N only uses data from rows 0..N.

DataKitchen:
  Splits the feature matrix into rolling train/test/live windows.
  This mimics FreqAI's rolling training: as new bars arrive, the oldest
  training bar is dropped and the newest is added, ensuring the model
  always describes the current market regime.

Reimplemented from FreqAI's conceptual architecture (AGPL) — no
verbatim code copy.  The rolling-window design and feature engineering
patterns are well-established in the ML finance literature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np


@dataclass
class CandleFeatures:
    """Feature matrix for one symbol's history."""

    feature_names: list[str]
    X: np.ndarray           # shape (N, F) — float64, NaN-free (NaN rows dropped)
    y: np.ndarray           # shape (N,) — labels (1=BUY, -1=SELL, 0=HOLD)
    timestamps: list[Any]   # length N — original timestamps for alignment


@dataclass
class DataWindow:
    """A train/test/live split of a CandleFeatures matrix."""

    X_train: np.ndarray
    y_train: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray
    X_live: np.ndarray      # the last ``live_rows`` rows — used for prediction
    feature_names: list[str]


class FeatureKitchen:
    """Converts OHLCV candle dicts into a normalised feature matrix.

    Each candle is a dict with keys: ``open``, ``high``, ``low``, ``close``,
    ``volume``.  The kitchen adds derived features (returns, log-returns,
    ATR-ratio, volume z-score etc.) and then z-score normalises each column.

    Usage::

        kitchen = FeatureKitchen()
        features = kitchen.build(candles, labels=labels)
    """

    DEFAULT_FEATURES = [
        "ret_1",     # 1-bar log return
        "ret_5",     # 5-bar log return
        "ret_20",    # 20-bar log return
        "vol_20",    # 20-bar rolling std of log returns
        "hl_ratio",  # (high-low)/close — daily range normalised
        "obv_roc_5", # 5-bar ROC of OBV
        "vol_z_20",  # volume z-score over 20 bars
        "sma_ratio", # close / SMA(20) - 1
        "ema_ratio", # close / EMA(20) - 1
        "rsi_14",    # RSI(14) normalised to [-1, 1]
    ]

    def __init__(
        self,
        feature_names: list[str] | None = None,
        normalise: bool = True,
    ) -> None:
        self._feature_names = feature_names or list(self.DEFAULT_FEATURES)
        self._normalise = normalise

    @property
    def feature_names(self) -> list[str]:
        return list(self._feature_names)

    def build(
        self,
        candles: list[dict[str, float]],
        labels: list[int] | None = None,
    ) -> CandleFeatures:
        """Build a feature matrix from a list of OHLCV dicts.

        ``candles`` is oldest-first.  ``labels`` must be the same length if
        provided; defaults to zeros.
        """
        n = len(candles)
        if n < 21:
            return CandleFeatures(
                feature_names=self._feature_names,
                X=np.zeros((0, len(self._feature_names))),
                y=np.zeros(0),
                timestamps=[],
            )

        close = np.array([c["close"] for c in candles], dtype=float)
        high  = np.array([c["high"]  for c in candles], dtype=float)
        low   = np.array([c["low"]   for c in candles], dtype=float)
        vol   = np.array([c.get("volume", 1.0) for c in candles], dtype=float)
        ts    = [c.get("ts", i) for i, c in enumerate(candles)]

        # Build each feature column
        feat_map: dict[str, np.ndarray] = {}
        log_ret = np.full(n, np.nan)
        log_ret[1:] = np.log(close[1:] / close[:-1])

        feat_map["ret_1"] = log_ret
        feat_map["ret_5"] = self._rolling_sum(log_ret, 5)
        feat_map["ret_20"] = self._rolling_sum(log_ret, 20)
        feat_map["vol_20"] = self._rolling_std(log_ret, 20)
        feat_map["hl_ratio"] = np.where(close > 0, (high - low) / close, np.nan)
        feat_map["obv_roc_5"] = self._obv_roc(close, vol, 5)
        feat_map["vol_z_20"] = self._z_score(vol, 20)
        feat_map["sma_ratio"] = self._ratio_to_sma(close, 20)
        feat_map["ema_ratio"] = self._ratio_to_ema(close, 20)
        feat_map["rsi_14"]   = (self._rsi(close, 14) - 50.0) / 50.0

        # Build matrix
        cols = [feat_map.get(f, np.full(n, np.nan)) for f in self._feature_names]
        X_raw = np.column_stack(cols)

        # Drop NaN rows
        valid_mask = ~np.any(np.isnan(X_raw), axis=1)
        X_clean = X_raw[valid_mask]
        ts_clean = [ts[i] for i in range(n) if valid_mask[i]]

        lbl_arr: np.ndarray
        if labels is not None:
            lbl_raw = np.array(labels[:n], dtype=float)
            lbl_arr = lbl_raw[valid_mask]
        else:
            lbl_arr = np.zeros(len(X_clean))

        if self._normalise and len(X_clean) > 1:
            means = X_clean.mean(axis=0)
            stds  = X_clean.std(axis=0, ddof=1)
            stds  = np.where(stds == 0, 1.0, stds)
            X_clean = (X_clean - means) / stds

        return CandleFeatures(
            feature_names=self._feature_names,
            X=X_clean,
            y=lbl_arr,
            timestamps=ts_clean,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rolling_sum(arr: np.ndarray, window: int) -> np.ndarray:
        out = np.full(len(arr), np.nan)
        for i in range(window, len(arr)):
            out[i] = np.nansum(arr[i - window + 1 : i + 1])
        return out

    @staticmethod
    def _rolling_std(arr: np.ndarray, window: int) -> np.ndarray:
        out = np.full(len(arr), np.nan)
        for i in range(window, len(arr)):
            window_data = arr[i - window + 1 : i + 1]
            if not np.any(np.isnan(window_data)):
                out[i] = window_data.std(ddof=1)
        return out

    @staticmethod
    def _z_score(arr: np.ndarray, window: int) -> np.ndarray:
        out = np.full(len(arr), np.nan)
        for i in range(window, len(arr)):
            w = arr[i - window + 1 : i + 1]
            mu, sigma = w.mean(), w.std(ddof=1)
            out[i] = (arr[i] - mu) / sigma if sigma > 0 else 0.0
        return out

    @staticmethod
    def _ratio_to_sma(close: np.ndarray, window: int) -> np.ndarray:
        out = np.full(len(close), np.nan)
        for i in range(window - 1, len(close)):
            sma = close[i - window + 1 : i + 1].mean()
            out[i] = close[i] / sma - 1 if sma != 0 else np.nan
        return out

    @staticmethod
    def _ratio_to_ema(close: np.ndarray, window: int) -> np.ndarray:
        out = np.full(len(close), np.nan)
        k = 2.0 / (window + 1)
        prev = close[0]
        for i in range(len(close)):
            prev = close[i] * k + prev * (1 - k)
            if i >= window - 1:
                out[i] = close[i] / prev - 1 if prev != 0 else np.nan
        return out

    @staticmethod
    def _obv_roc(close: np.ndarray, vol: np.ndarray, period: int) -> np.ndarray:
        obv = np.zeros(len(close))
        obv[0] = vol[0]
        for i in range(1, len(close)):
            sign = 1 if close[i] > close[i - 1] else (-1 if close[i] < close[i - 1] else 0)
            obv[i] = obv[i - 1] + sign * vol[i]
        out = np.full(len(close), np.nan)
        for i in range(period, len(close)):
            if obv[i - period] != 0:
                out[i] = (obv[i] / obv[i - period] - 1) * 100
        return out

    @staticmethod
    def _rsi(close: np.ndarray, length: int) -> np.ndarray:
        n = len(close)
        out = np.full(n, np.nan)
        diff = np.diff(close)
        gains = np.where(diff > 0, diff, 0.0)
        losses = np.where(diff < 0, -diff, 0.0)
        if n <= length:
            return out
        avg_gain = gains[:length].mean()
        avg_loss = losses[:length].mean()
        for i in range(length, n - 1):
            avg_gain = (avg_gain * (length - 1) + gains[i]) / length
            avg_loss = (avg_loss * (length - 1) + losses[i]) / length
            if avg_gain == 0 and avg_loss == 0:
                out[i + 1] = 50.0
            elif avg_loss == 0:
                out[i + 1] = 100.0
            else:
                rs = avg_gain / avg_loss
                out[i + 1] = 100 - 100 / (1 + rs)
        out[:length] = np.nan
        return out


class DataKitchen:
    """Splits feature matrices into rolling train/test/live windows.

    ``train_ratio``  — fraction of data used for training (default 0.8)
    ``test_ratio``   — fraction used for out-of-sample test (default 0.1)
    ``live_rows``    — number of most-recent rows returned as ``X_live``
                       (default 1 — the latest bar for prediction)
    """

    def __init__(
        self,
        train_ratio: float = 0.80,
        test_ratio:  float = 0.10,
        live_rows:   int   = 1,
    ) -> None:
        if train_ratio + test_ratio > 1.0:
            raise ValueError("train_ratio + test_ratio must be ≤ 1.0")
        self.train_ratio = train_ratio
        self.test_ratio  = test_ratio
        self.live_rows   = live_rows

    def split(self, features: CandleFeatures) -> DataWindow:
        """Return a DataWindow from the full feature matrix."""
        X, y = features.X, features.y
        n = len(X)
        if n == 0:
            empty = np.zeros((0, X.shape[1] if X.ndim > 1 else 0))
            return DataWindow(
                X_train=empty, y_train=np.zeros(0),
                X_test=empty,  y_test=np.zeros(0),
                X_live=empty,  feature_names=features.feature_names,
            )
        train_end = int(n * self.train_ratio)
        test_end  = train_end + int(n * self.test_ratio)
        return DataWindow(
            X_train=X[:train_end],
            y_train=y[:train_end],
            X_test=X[train_end:test_end],
            y_test=y[train_end:test_end],
            X_live=X[-self.live_rows:],
            feature_names=features.feature_names,
        )
