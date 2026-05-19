"""Train the Regime-Trader HMM model using NIFTY 50 + SENSEX data from Zerodha Kite.

Usage (first run — needs browser login):
    python scripts/train_regime_hmm.py

Usage (subsequent runs — access token already saved in .env.zerodha):
    python scripts/train_regime_hmm.py

Authentication flow:
  1. Script prints a Kite login URL.
  2. Open it in your browser, log in with your Zerodha credentials.
  3. After login, copy the full redirect URL (or just the request_token param).
  4. Paste it back here — the script exchanges it for an access_token,
     saves it to .env.zerodha, and proceeds with data fetch and training.

Credentials are read from  backend/.env.zerodha  (never committed).
"""

from __future__ import annotations

import os
import pickle
import re
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from hmmlearn import hmm
from kiteconnect import KiteConnect
from sklearn.preprocessing import StandardScaler

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
ENV_FILE    = BACKEND_DIR / ".env.zerodha"
MODEL_DIR   = BACKEND_DIR / "app" / "strategies" / "ml" / "regime_trader" / "models" / "v1"
MODEL_FILE  = MODEL_DIR / "model.pkl"

# ── Config ────────────────────────────────────────────────────────────────────
N_REGIMES    = 5
LOOKBACK_YRS = 5          # years of daily history to pull
REGIMES      = ["Crash", "Bear", "Neutral", "Bull", "Euphoria"]

# Yahoo Finance tickers for Indian indices
# Zerodha historical data requires a paid add-on; yfinance is free and reliable.
INSTRUMENTS = [
    {"label": "NIFTY 50", "yf_ticker": "^NSEI"},
    {"label": "SENSEX",   "yf_ticker": "^BSESN"},
]


# ── Env helpers ───────────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
    """Load key=value pairs from .env.zerodha into a dict."""
    env: dict[str, str] = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _save_access_token(token: str) -> None:
    """Persist access_token back to .env.zerodha so reruns skip login."""
    text = ENV_FILE.read_text()
    if "ZERODHA_ACCESS_TOKEN=" in text:
        text = re.sub(r"ZERODHA_ACCESS_TOKEN=.*", f"ZERODHA_ACCESS_TOKEN={token}", text)
    else:
        text += f"\nZERODHA_ACCESS_TOKEN={token}\n"
    ENV_FILE.write_text(text)
    print(f"[AUTH] Access token saved to {ENV_FILE.name}")


# ── Authentication ────────────────────────────────────────────────────────────

def authenticate(env: dict[str, str]) -> KiteConnect:
    """Return an authenticated KiteConnect instance.

    If a valid access_token is stored in .env.zerodha, it is reused.
    Otherwise, the full OAuth login flow is triggered interactively.
    """
    api_key    = env.get("ZERODHA_API_KEY", "")
    api_secret = env.get("ZERODHA_API_SECRET", "")

    if not api_key or not api_secret:
        print("[ERROR] ZERODHA_API_KEY and ZERODHA_API_SECRET must be set in .env.zerodha")
        sys.exit(1)

    kite = KiteConnect(api_key=api_key)

    # Try reusing a saved access token first
    saved_token = env.get("ZERODHA_ACCESS_TOKEN", "").strip()
    if saved_token:
        try:
            kite.set_access_token(saved_token)
            profile = kite.profile()          # quick validation call
            print(f"[AUTH] Reusing saved token — logged in as {profile['user_name']}")
            return kite
        except Exception:
            print("[AUTH] Saved token expired — starting fresh login")

    # --- Full OAuth flow ---
    login_url = kite.login_url()
    print("\n" + "=" * 60)
    print("  Zerodha Kite Login Required")
    print("=" * 60)
    print(f"\n  1. Opening login URL in your browser...")
    print(f"     {login_url}")
    print("\n  2. Log in with your Zerodha credentials.")
    print("  3. After login, copy the FULL redirect URL from the browser")
    print("     address bar (it contains request_token=XXXX).")
    print()

    # Check if token was supplied via CLI arg (non-interactive mode)
    if env.get("_cli_request_token"):
        request_token = env["_cli_request_token"]
        print(f"[AUTH] Using request_token from --request-token flag")
    else:
        try:
            webbrowser.open(login_url)
        except Exception:
            pass                          # headless env — user opens manually

        raw = input("  Paste the redirect URL (or just the request_token): ").strip()
        match = re.search(r"request_token=([A-Za-z0-9]+)", raw)
        request_token = match.group(1) if match else raw

    if not request_token:
        print("[ERROR] No request_token found. Exiting.")
        sys.exit(1)

    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]
    kite.set_access_token(access_token)
    _save_access_token(access_token)

    profile = kite.profile()
    print(f"\n[AUTH] Logged in as {profile['user_name']} ({profile['email']})")
    return kite


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_ohlcv(instrument: dict, years: int) -> pd.DataFrame | None:
    """Fetch `years` of daily OHLCV from Yahoo Finance for an Indian index.

    Note: Zerodha historical data requires a paid add-on subscription.
    Yahoo Finance provides free, reliable daily OHLCV for NSE/BSE indices.
    """
    label  = instrument["label"]
    ticker = instrument["yf_ticker"]

    end   = datetime.now()
    start = end - timedelta(days=years * 366)

    try:
        raw = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
    except Exception as exc:
        print(f"[ERROR] yfinance could not fetch {label}: {exc}")
        return None

    if raw is None or len(raw) == 0:
        print(f"[WARN] No records returned for {label} ({ticker})")
        return None

    # Flatten MultiIndex columns if present (yfinance >= 0.2 returns MultiIndex)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["open", "close"])

    # Indices often have 0 volume in Yahoo Finance — replace with 1 so log() works
    df["volume"] = df["volume"].replace(0, 1).fillna(1)

    df.index = pd.to_datetime(df.index).tz_localize(None)   # strip tz

    print(f"[YF]   {label} ({ticker}): {len(df)} daily bars  "
          f"({df.index[0].date()} to {df.index[-1].date()})")
    return df


# ── Feature engineering ───────────────────────────────────────────────────────

def extract_features(df: pd.DataFrame) -> np.ndarray:
    """5-dim feature vector: log-returns (1/5/20-bar), volatility, volume."""
    close  = df["close"].astype(float).values
    volume = df["volume"].astype(float).values

    log_ret = np.diff(np.log(np.where(close > 0, close, 1e-9)), prepend=0.0)
    ret_1   = log_ret
    ret_5   = pd.Series(log_ret).rolling(5,  min_periods=1).sum().values
    ret_20  = pd.Series(log_ret).rolling(20, min_periods=1).sum().values
    vol_20  = pd.Series(log_ret).rolling(20, min_periods=1).std().fillna(0).values

    vol_ma  = pd.Series(volume).rolling(20, min_periods=1).mean().values
    vol_log = np.log(np.where(vol_ma > 0, vol_ma, 1.0))

    X = np.column_stack([ret_1, ret_5, ret_20, vol_20, vol_log])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


# ── Training ──────────────────────────────────────────────────────────────────

def build_remap(model: hmm.GaussianHMM) -> dict[int, int]:
    """Map raw HMM state IDs to named regime IDs sorted by volatility.

    Highest volatility state -> Crash (0), lowest -> Euphoria (4).
    """
    vol_means = model.means_[:, 3]           # feature index 3 = vol_20
    rank      = np.argsort(vol_means)[::-1]  # descending
    return {int(old): int(new) for new, old in enumerate(rank)}


def train(Xs: list[np.ndarray], scaler: StandardScaler) -> hmm.GaussianHMM:
    """Scale all feature matrices and fit a multi-sequence GaussianHMM."""
    X_all   = np.vstack(Xs)
    X_all   = scaler.fit_transform(X_all)
    lengths = [len(X) for X in Xs]

    model = hmm.GaussianHMM(
        n_components=N_REGIMES,
        covariance_type="full",
        n_iter=1000,
        random_state=42,
        verbose=False,
    )
    model.fit(X_all, lengths)
    ll = model.score(X_all)
    print(f"[HMM] Trained on {sum(lengths)} bars, {len(lengths)} sequences  "
          f"(log-likelihood {ll:.2f})")
    return model


# ── Reporting ─────────────────────────────────────────────────────────────────

def print_stats(model: hmm.GaussianHMM, remap: dict[int, int]) -> None:
    print("\n[HMM] State means  (ret1 / ret5 / ret20 / vol20 / logvol — standardised):")
    for raw, mean in enumerate(model.means_):
        name = REGIMES[remap[raw]]
        print(f"  state{raw} -> {name:>10}: "
              f"ret1={mean[0]:+.3f}  ret5={mean[1]:+.3f}  vol={mean[3]:+.3f}")

    print("\n[HMM] Transition matrix (raw states):")
    print(np.round(model.transmat_, 3))


def print_summary(df: pd.DataFrame, labels: np.ndarray, symbol: str, n: int = 30) -> None:
    subset = df.tail(n).copy()
    subset["regime"] = [REGIMES[l] for l in labels[-n:]]
    print(f"\n{'-' * 56}")
    print(f"  Last {n} daily bars  --  {symbol}")
    print(f"{'-' * 56}")
    print(subset[["close", "regime"]].to_string())
    print(f"{'-' * 56}\n")

    counts = pd.Series([REGIMES[l] for l in labels]).value_counts()
    print(f"  Full-history regime distribution ({len(labels)} bars):")
    for name in REGIMES:
        cnt = counts.get(name, 0)
        pct = cnt / len(labels) * 100
        bar = "#" * int(pct / 2)
        print(f"  {name:>10}: {bar:<28}  {cnt:4d}  ({pct:.1f}%)")
    print()


def print_transitions(labels: np.ndarray, index: pd.DatetimeIndex) -> None:
    changes = [
        (index[i].date(), REGIMES[labels[i - 1]], REGIMES[labels[i]])
        for i in range(1, len(labels))
        if labels[i] != labels[i - 1]
    ]
    print(f"  Regime transitions detected: {len(changes)}")
    for date, frm, to in changes[-15:]:
        print(f"    {date}   {frm:>10} -> {to}")
    print()


# ── Persistence ───────────────────────────────────────────────────────────────

def save_model(model: hmm.GaussianHMM, scaler: StandardScaler,
               remap: dict[int, int], symbols: list[str]) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model":      model,
        "scaler":     scaler,
        "remap":      remap,
        "regimes":    REGIMES,
        "symbols":    symbols,
        "source":     "zerodha_kite",
        "trained_at": datetime.utcnow().isoformat(),
    }
    with open(MODEL_FILE, "wb") as f:
        pickle.dump(payload, f)
    size_kb = MODEL_FILE.stat().st_size / 1024
    print(f"[SAVE] Model saved -> {MODEL_FILE}  ({size_kb:.1f} KB)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Train Regime-Trader HMM via Zerodha Kite")
    parser.add_argument(
        "--request-token", "-t",
        default="",
        help="Zerodha request_token from the login redirect URL. "
             "If omitted, the script prints the login URL and waits for input.",
    )
    args = parser.parse_args()

    print("=" * 56)
    print("  DRUVA Regime-Trader -- HMM Training via Zerodha Kite")
    print(f"  Instruments : NIFTY 50 + SENSEX  (Indian indices)")
    print(f"  History     : {LOOKBACK_YRS} years daily  |  Regimes: {N_REGIMES}")
    print("=" * 56 + "\n")

    # 1. Auth (validates Zerodha session; access token saved for DRUVA broker use)
    env  = _load_env()
    if args.request_token:
        env["_cli_request_token"] = args.request_token.strip()
    authenticate(env)   # side-effect: saves access_token to .env.zerodha

    # 2. Fetch (Yahoo Finance — free, no subscription needed)
    print("[DATA] Fetching NIFTY 50 + SENSEX from Yahoo Finance ...")
    dfs: dict[str, pd.DataFrame] = {}
    for inst in INSTRUMENTS:
        df = fetch_ohlcv(inst, LOOKBACK_YRS)
        if df is not None and len(df) >= 100:
            dfs[inst["label"]] = df

    if not dfs:
        print("[ERROR] No usable data. Exiting.")
        sys.exit(1)

    # 3. Features
    scaler = StandardScaler()
    Xs     = [extract_features(df) for df in dfs.values()]

    # 4. Train
    print(f"\n[HMM] Training {N_REGIMES}-state GaussianHMM ...")
    model = train(Xs, scaler)
    remap = build_remap(model)

    # 5. Label primary (NIFTY 50 or first available)
    primary_label = list(dfs.keys())[0]
    primary_df    = dfs[primary_label]
    X_primary     = extract_features(primary_df)
    X_scaled      = scaler.transform(X_primary)
    raw_states    = model.predict(X_scaled)
    labels        = np.array([remap[int(s)] for s in raw_states])
    proba         = model.predict_proba(X_scaled)

    # 6. Report
    print_stats(model, remap)
    print_summary(primary_df, labels, primary_label, n=30)
    print_transitions(labels, primary_df.index)

    # 7. Save
    save_model(model, scaler, remap, list(dfs.keys()))

    # 8. Final status
    current_id    = int(labels[-1])
    current_name  = REGIMES[current_id]
    confidence    = float(proba[-1].max())
    allocation    = [5, 30, 50, 95, 80][current_id]

    print("=" * 56)
    print(f"  Current Regime : {current_name}  (id={current_id})")
    print(f"  Confidence     : {confidence:.1%}")
    print(f"  Allocation     : {allocation}%")
    print(f"  Symbol         : {primary_label}")
    print(f"  As of          : {primary_df.index[-1].date()}")
    print("=" * 56)
    print("\nTraining complete. Model ready for DRUVA.\n")


if __name__ == "__main__":
    main()
