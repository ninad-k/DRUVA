"""Train the Regime-Trader HMM model using live data from MetaTrader 5.

Usage:
    python scripts/train_regime_hmm.py

This script:
  1. Connects to the locally running MT5 terminal
  2. Fetches historical daily OHLCV for XAUUSD + EURUSD (3 years)
  3. Trains a 5-state GaussianHMM
  4. Saves the model to models/v1/model.pkl
  5. Prints a regime summary for the latest 30 days
"""

import sys
import pickle
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from sklearn.preprocessing import StandardScaler
from hmmlearn import hmm

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BACKEND_DIR  = SCRIPT_DIR.parent
MODEL_DIR    = BACKEND_DIR / "app" / "strategies" / "ml" / "regime_trader" / "models" / "v1"
MODEL_FILE   = MODEL_DIR / "model.pkl"

# ── Config ────────────────────────────────────────────────────────────────────
N_REGIMES    = 5
SYMBOLS      = ["XAUUSD", "EURUSD"]     # Primary training symbols
LOOKBACK_YRS = 3                         # Years of history to pull
TIMEFRAME    = mt5.TIMEFRAME_D1          # Daily bars
REGIMES      = ["Crash", "Bear", "Neutral", "Bull", "Euphoria"]


def connect_mt5() -> bool:
    """Initialize MT5 connection."""
    if not mt5.initialize():
        print(f"[ERROR] MT5 init failed: {mt5.last_error()}")
        return False
    info = mt5.terminal_info()
    acct  = mt5.account_info()
    print(f"[MT5] Connected  — {info.company}")
    print(f"[MT5] Account    — {acct.login} @ {acct.server}")
    print(f"[MT5] Balance    — {acct.currency} {acct.balance:,.2f}")
    return True


def fetch_ohlcv(symbol: str, years: int) -> pd.DataFrame | None:
    """Pull `years` worth of daily OHLCV from MT5."""
    # Ensure symbol is visible in Market Watch
    if not mt5.symbol_select(symbol, True):
        print(f"[WARN] Could not select {symbol}")

    n_bars = years * 365          # generous upper bound; MT5 returns trading days
    rates  = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n_bars)

    if rates is None or len(rates) == 0:
        print(f"[ERROR] No data for {symbol}: {mt5.last_error()}")
        return None

    df = pd.DataFrame(rates)
    df["time"]   = pd.to_datetime(df["time"], unit="s")
    df           = df.set_index("time")
    df           = df.rename(columns={"tick_volume": "volume"})[
        ["open", "high", "low", "close", "volume"]
    ]
    df           = df.dropna()
    print(f"[MT5] {symbol}: {len(df)} daily bars  "
          f"({df.index[0].date()} to {df.index[-1].date()})")
    return df


def extract_features(df: pd.DataFrame) -> np.ndarray:
    """Compute 5-dim feature vector: returns + volatility + volume."""
    close   = df["close"].astype(float).values
    volume  = df["volume"].astype(float).values

    # Log returns
    log_ret = np.diff(np.log(np.where(close > 0, close, 1e-9)), prepend=0.0)

    ret_1  = log_ret
    ret_5  = pd.Series(log_ret).rolling(5,  min_periods=1).sum().values
    ret_20 = pd.Series(log_ret).rolling(20, min_periods=1).sum().values

    vol_20 = pd.Series(log_ret).rolling(20, min_periods=1).std().values

    vol_ma  = pd.Series(volume).rolling(20, min_periods=1).mean().values
    vol_ma  = np.where(vol_ma > 0, vol_ma, 1.0)
    vol_log = np.log(vol_ma)

    X = np.column_stack([ret_1, ret_5, ret_20, vol_20, vol_log])
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return X


def train(Xs: list[np.ndarray], scaler: StandardScaler) -> hmm.GaussianHMM:
    """Scale features, combine all symbols, fit HMM."""
    # Fit scaler on all data combined
    X_all = np.vstack(Xs)
    X_all = scaler.fit_transform(X_all)

    # Lengths for multi-sequence HMM training
    lengths = [len(X) for X in Xs]
    X_scaled_parts = []
    offset = 0
    for l in lengths:
        X_scaled_parts.append(X_all[offset:offset+l])
        offset += l

    model = hmm.GaussianHMM(
        n_components=N_REGIMES,
        covariance_type="full",
        n_iter=1000,
        random_state=42,
        verbose=False,
    )
    model.fit(X_all, lengths)
    print(f"[HMM] Trained on {sum(lengths)} total bars across {len(lengths)} symbols")
    return model


def build_remap(model: hmm.GaussianHMM) -> dict:
    """Build state_id -> regime_id mapping sorted by volatility.

    Sorts HMM states by their mean volatility (feature index 3).
    Most volatile state -> Crash (0), least volatile -> Euphoria (4).
    Returns remap dict: {raw_state_id: regime_id}.
    """
    means    = model.means_[:, 3]        # vol_20 mean per state
    rank     = np.argsort(means)[::-1]   # descending: highest vol = Crash
    remap    = {int(old): int(new) for new, old in enumerate(rank)}
    return remap


def label_regimes(model: hmm.GaussianHMM, X_scaled: np.ndarray) -> tuple:
    """Predict regime IDs mapped to named regime indices."""
    raw_states = model.predict(X_scaled)
    remap      = build_remap(model)
    labelled   = np.array([remap[s] for s in raw_states])
    return labelled, remap


def print_regime_summary(df: pd.DataFrame, labels: np.ndarray, n: int = 30) -> None:
    """Print the last n bars with detected regimes."""
    subset = df.tail(n).copy()
    subset["regime_id"]   = labels[-n:]
    subset["regime_name"] = subset["regime_id"].map(dict(enumerate(REGIMES)))
    cols = ["close", "regime_id", "regime_name"]
    print(f"\n{'-'*52}")
    print(f"  Last {n} daily bars - Regime detection (XAUUSD)")
    print(f"{'-'*52}")
    print(subset[cols].to_string())
    print(f"{'-'*52}\n")

    counts = subset["regime_name"].value_counts()
    print("  Regime distribution (last 30 days):")
    for name, cnt in counts.items():
        bar = "#" * int(cnt * 1.5)
        print(f"  {name:>10}: {bar}  ({cnt})")
    print()


def save_model(model: hmm.GaussianHMM, scaler: StandardScaler, remap: dict) -> None:
    """Persist model, scaler, and regime remap to disk."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model":   model,
        "scaler":  scaler,
        "remap":   remap,
        "regimes": REGIMES,
        "symbols": SYMBOLS,
        "trained_at": datetime.utcnow().isoformat(),
    }
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(payload, f)
    size_kb = MODEL_FILE.stat().st_size / 1024
    print(f"[SAVE] Model saved -> {MODEL_FILE}  ({size_kb:.1f} KB)")


def print_model_stats(model: hmm.GaussianHMM, remap: dict) -> None:
    """Print HMM internals for debugging."""
    print("\n[HMM] State means (features: ret1, ret5, ret20, vol20, logvol):")
    for raw_state, mean in enumerate(model.means_):
        regime_id   = remap[raw_state]
        regime_name = REGIMES[regime_id]
        print(f"  state{raw_state} -> {regime_name:>10} (regime {regime_id}): "
              f"ret1={mean[0]:+.4f}  vol={mean[3]:.4f}")

    print("\n[HMM] Transition matrix (raw states):")
    print(np.round(model.transmat_, 3))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 56)
    print("  DRUVA Regime-Trader - HMM Training via MT5")
    print("=" * 56)

    # 1. Connect
    if not connect_mt5():
        sys.exit(1)

    # 2. Fetch data for all symbols
    dfs = {}
    for sym in SYMBOLS:
        df = fetch_ohlcv(sym, LOOKBACK_YRS)
        if df is not None and len(df) >= 100:
            dfs[sym] = df

    mt5.shutdown()

    if not dfs:
        print("[ERROR] No usable data fetched. Exiting.")
        sys.exit(1)

    # 3. Extract features per symbol
    scaler = StandardScaler()
    Xs     = [extract_features(df) for df in dfs.values()]

    # 4. Train HMM
    print(f"\n[HMM] Training {N_REGIMES}-state GaussianHMM ...")
    model = train(Xs, scaler)
    print(f"[HMM] Score (log-likelihood): {model.score(scaler.transform(Xs[0])):.2f}")

    # 5. Label regimes (primary symbol = first in dfs)
    primary_sym = list(dfs.keys())[0]
    primary_df  = dfs[primary_sym]
    X_primary   = extract_features(primary_df)
    X_scaled    = scaler.transform(X_primary)
    labels, remap = label_regimes(model, X_scaled)

    # 6. Print diagnostics
    print_model_stats(model, remap)
    print_regime_summary(primary_df, labels, n=30)

    # 7. Save
    save_model(model, scaler, remap)

    # Final regime
    current_regime_id   = int(labels[-1])
    current_regime_name = REGIMES[current_regime_id]
    proba = model.predict_proba(X_scaled)
    confidence = float(proba[-1].max())

    print(f"\n{'='*56}")
    print(f"  Current Regime : {current_regime_name}  (ID={current_regime_id})")
    print(f"  Confidence     : {confidence:.1%}")
    print(f"  Symbol         : {primary_sym}")
    print(f"  As of          : {primary_df.index[-1].date()}")
    print(f"{'='*56}")
    print("")
    print("Training complete. Model ready for DRUVA.")


if __name__ == "__main__":
    main()
