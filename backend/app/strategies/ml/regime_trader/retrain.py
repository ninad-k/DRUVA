"""Shared retrain logic for regime-trader HMM.

Called by:
  - POST /api/v1/strategies/regime-trader/retrain (on-demand)
  - APScheduler cron job (weekly Sunday 01:00 UTC)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pickle

import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.preprocessing import StandardScaler

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models" / "v1"
MODEL_FILE = MODEL_DIR / "model.pkl"

N_REGIMES = 5
REGIMES = ["Crash", "Bear", "Neutral", "Bull", "Euphoria"]

INSTRUMENTS = [
    {"label": "NIFTY 50", "yf_ticker": "^NSEI"},
    {"label": "SENSEX",   "yf_ticker": "^BSESN"},
]

LOOKBACK_YEARS = 5


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def _build_features(close: pd.Series) -> pd.DataFrame:
    """Return the 5-dimensional feature matrix used for HMM training.

    Features
    --------
    ret_1    — 1-day log return
    ret_5    — 5-day log return
    ret_20   — 20-day log return
    vol_20   — 20-day rolling volatility (std of log returns)
    log_vol  — log(vol_20 + 1e-8), stabilises the heavy-tailed distribution
    """
    log_ret = np.log(close / close.shift(1))

    ret_1  = log_ret
    ret_5  = np.log(close / close.shift(5))
    ret_20 = np.log(close / close.shift(20))
    vol_20 = log_ret.rolling(20).std()
    log_vol = np.log(vol_20.clip(lower=1e-8))

    df = pd.DataFrame(
        {
            "ret_1":   ret_1,
            "ret_5":   ret_5,
            "ret_20":  ret_20,
            "vol_20":  vol_20,
            "log_vol": log_vol,
        }
    )
    return df


def _fetch_and_combine() -> tuple[pd.DataFrame, list[str]]:
    """Download NIFTY 50 + SENSEX via yfinance and return a combined feature matrix.

    Returns
    -------
    (features_df, symbols)
        features_df — rows = trading days (NaN rows dropped), cols = 5 features
        symbols     — list of yfinance tickers actually downloaded
    """
    import yfinance as yf  # import locally — heavy optional dep

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_YEARS * 365 + 30)  # a little extra

    frames: list[pd.DataFrame] = []
    symbols: list[str] = []

    for inst in INSTRUMENTS:
        ticker = inst["yf_ticker"]
        label  = inst["label"]
        logger.info("retrain.downloading", symbol=ticker, label=label)
        try:
            raw = yf.download(
                ticker,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=True,
            )
            if raw.empty:
                logger.warning("retrain.download_empty", symbol=ticker)
                continue
            # yfinance returns a MultiIndex when multiple tickers requested;
            # single ticker gives a plain DataFrame with column "Close".
            close = raw["Close"].squeeze()
            feats = _build_features(close)
            frames.append(feats)
            symbols.append(ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrain.download_failed", symbol=ticker, error=str(exc))

    if not frames:
        raise RuntimeError("No data downloaded for any instrument; cannot train.")

    # Average the feature matrices across instruments (align on date index).
    combined = pd.concat(frames).groupby(level=0).mean()
    combined.dropna(inplace=True)
    combined.sort_index(inplace=True)

    return combined, symbols


# ---------------------------------------------------------------------------
# Core retrain function
# ---------------------------------------------------------------------------

def retrain_regime_hmm() -> dict[str, object]:
    """Fetch data, train HMM, save model.

    Returns
    -------
    dict with keys:
        trained_at     — ISO-8601 timestamp (UTC)
        symbols        — list of yfinance tickers used
        log_likelihood — final model log-likelihood (float)
        regime         — current regime name (str)
        confidence     — model confidence for current regime (float 0-1)
    """
    logger.info("retrain.started")

    # 1. Data
    features_df, symbols = _fetch_and_combine()
    X_raw = features_df.values.astype(np.float64)

    if len(X_raw) < 100:
        raise ValueError(
            f"Insufficient data after feature engineering: {len(X_raw)} rows. "
            "Need at least 100 trading days."
        )

    # 2. Scaling
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    # 3. Train GaussianHMM
    logger.info("retrain.training", n_samples=len(X), n_regimes=N_REGIMES)
    model = hmm.GaussianHMM(
        n_components=N_REGIMES,
        covariance_type="full",
        n_iter=1000,
        random_state=42,
        verbose=False,
    )
    model.fit(X)
    log_likelihood = float(model.score(X))
    logger.info("retrain.trained", log_likelihood=log_likelihood)

    # 4. Remap: sort states by vol_20 mean descending
    #    (state 0 = highest volatility → "Crash"; state 4 = lowest → "Euphoria"
    #     semantically this maps the HMM's internal state ids to economic labels)
    vol_col_idx = features_df.columns.get_loc("vol_20")
    state_means = model.means_  # shape: (n_regimes, n_features)
    # vol_20 mean per HMM state (in scaled space — ordering is still valid)
    state_vol_means = state_means[:, vol_col_idx]
    remap: dict[int, int] = {
        int(orig): int(new_idx)
        for new_idx, orig in enumerate(np.argsort(state_vol_means)[::-1])
    }

    # 5. Current regime — predict last row
    hidden_states = model.predict(X)
    last_raw_state = int(hidden_states[-1])
    current_regime_idx = remap[last_raw_state]
    current_regime = REGIMES[current_regime_idx]

    # Confidence: posterior probability for the last observation
    posteriors = model.predict_proba(X)
    last_posteriors = posteriors[-1]  # shape: (n_regimes,)
    confidence = float(last_posteriors[last_raw_state])

    # 6. Save artifact
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(timezone.utc)
    artifact = {
        "model":      model,
        "scaler":     scaler,
        "remap":      remap,
        "regimes":    REGIMES,
        "symbols":    symbols,
        "source":     "yfinance",
        "trained_at": trained_at.isoformat(),
    }
    with open(MODEL_FILE, "wb") as fh:
        pickle.dump(artifact, fh, protocol=5)

    logger.info(
        "retrain.saved",
        path=str(MODEL_FILE),
        regime=current_regime,
        confidence=round(confidence, 4),
    )

    return {
        "trained_at":     trained_at.isoformat(),
        "symbols":        symbols,
        "log_likelihood": log_likelihood,
        "regime":         current_regime,
        "confidence":     confidence,
    }
