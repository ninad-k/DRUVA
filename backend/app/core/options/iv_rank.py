"""IV Rank and IV Percentile calculator for options strategy selection.

IV Rank: Where current IV sits relative to 52-week high/low.
  IV Rank = (Current IV - 52w Low) / (52w High - 52w Low) * 100

IV Percentile: % of days in past year where IV was LOWER than current IV.
  (More statistically robust than IV Rank)

PCR (Put-Call Ratio): Put OI / Call OI
  PCR > 1.2 → Bullish contrarian (fear elevated, market likely to bounce)
  PCR < 0.7 → Bearish contrarian (complacency, market likely to fall)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx

from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

# NSE headers required to avoid 403 responses
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

_NSE_OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"

# Module-level 3-minute cache: { cache_key: (result, timestamp) }
_CACHE: dict[str, tuple[object, float]] = {}
_CACHE_TTL_SECONDS = 180


def _cache_get(key: str) -> object | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    result, ts = entry
    if time.monotonic() - ts > _CACHE_TTL_SECONDS:
        del _CACHE[key]
        return None
    return result


def _cache_set(key: str, value: object) -> None:
    _CACHE[key] = (value, time.monotonic())


@dataclass
class IVSnapshot:
    """Point-in-time IV reading for an index."""

    symbol: str
    current_iv: float
    iv_rank: float          # 0–100, where 100 = at 52w high
    iv_percentile: float    # 0–100, % of days below current IV
    iv_52w_high: float
    iv_52w_low: float
    as_of: datetime
    interpretation: str     # "expensive" | "normal" | "cheap"


@dataclass
class PCRSnapshot:
    """Put-Call Ratio reading for an index option chain."""

    symbol: str
    pcr: float
    call_oi: int
    put_oi: int
    as_of: datetime
    signal: Literal["bullish", "bearish", "neutral"]


class IVRankCalculator:
    """Stateless calculator for IV Rank, IV Percentile, and PCR from NSE data."""

    # ------------------------------------------------------------------ math

    def compute_iv_rank(self, iv_history: list[float], current_iv: float) -> float:
        """IV Rank: (current - 52w_low) / (52w_high - 52w_low) * 100.

        Returns 0.0 if the history is empty or the range is zero.
        """
        if not iv_history:
            return 0.0
        low = min(iv_history)
        high = max(iv_history)
        if high - low < 1e-9:
            return 0.0
        rank = (current_iv - low) / (high - low) * 100.0
        return max(0.0, min(100.0, rank))

    def compute_iv_percentile(self, iv_history: list[float], current_iv: float) -> float:
        """IV Percentile: fraction of historical days where IV < current_iv, * 100.

        More robust than IV Rank because outlier spikes don't distort it.
        """
        if not iv_history:
            return 0.0
        below = sum(1 for v in iv_history if v < current_iv)
        return below / len(iv_history) * 100.0

    def interpret_iv(self, iv_rank: float, iv_percentile: float) -> str:
        """Classify IV environment for strategy selection.

        Rules (IV Rank takes primary precedence):
          - iv_rank > 50  → "expensive"  (sell premium)
          - iv_rank < 30  → "cheap"      (buy premium / avoid short vol)
          - otherwise     → "normal"
        """
        if iv_rank > 50:
            return "expensive"
        if iv_rank < 30:
            return "cheap"
        return "normal"

    # ----------------------------------------------------------- NSE fetches

    async def fetch_nifty_iv(self, client: httpx.AsyncClient) -> IVSnapshot:
        """Fetch the ATM IV for NIFTY from the NSE option chain API.

        Caches the result for 3 minutes (module-level cache).
        """
        cache_key = "nifty_iv"
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("iv_rank.fetch_nifty_iv: cache hit")
            return cached  # type: ignore[return-value]

        url = _NSE_OPTION_CHAIN_URL.format(symbol="NIFTY")
        logger.info("iv_rank.fetch_nifty_iv: fetching", url=url)

        resp = await client.get(url, headers=_NSE_HEADERS, timeout=15.0)
        resp.raise_for_status()
        payload = resp.json()

        records = payload.get("records", {})
        data_rows = records.get("data", [])
        underlying_value: float = float(records.get("underlyingValue", 0) or 0)

        # Find ATM strike (closest to spot)
        atm_strike: float = float(records.get("strikePrices", [underlying_value])[0])
        if underlying_value:
            all_strikes = [float(r.get("strikePrice", 0)) for r in data_rows if r.get("strikePrice")]
            if all_strikes:
                atm_strike = min(all_strikes, key=lambda k: abs(k - underlying_value))

        # Gather CE + PE IVs for the ATM strike across all expiries
        # (use nearest expiry for the headline ATM IV)
        atm_ivs: list[float] = []
        for row in data_rows:
            if float(row.get("strikePrice", -1)) != atm_strike:
                continue
            ce_data = row.get("CE", {})
            pe_data = row.get("PE", {})
            ce_iv = float(ce_data.get("impliedVolatility", 0) or 0)
            pe_iv = float(pe_data.get("impliedVolatility", 0) or 0)
            if ce_iv > 0:
                atm_ivs.append(ce_iv)
            if pe_iv > 0:
                atm_ivs.append(pe_iv)
            if atm_ivs:
                # Use the first expiry with valid IVs
                break

        current_iv = sum(atm_ivs) / len(atm_ivs) if atm_ivs else 0.0

        # Build a synthetic 52-week history from ALL strikes / expiries
        # (real usage would pass stored daily IV snapshots; here we approximate
        # from the cross-section available in the chain)
        all_ivs: list[float] = []
        for row in data_rows:
            ce_data = row.get("CE", {})
            pe_data = row.get("PE", {})
            for iv_val in [ce_data.get("impliedVolatility"), pe_data.get("impliedVolatility")]:
                if iv_val and float(iv_val) > 0:
                    all_ivs.append(float(iv_val))

        # iv_rank & iv_percentile require a historical series; here we use the
        # cross-section as a proxy. Callers with stored history should pass it
        # to compute_iv_rank / compute_iv_percentile directly.
        iv_rank = self.compute_iv_rank(all_ivs, current_iv) if all_ivs else 0.0
        iv_percentile = self.compute_iv_percentile(all_ivs, current_iv) if all_ivs else 0.0
        iv_52w_high = max(all_ivs) if all_ivs else current_iv
        iv_52w_low = min(all_ivs) if all_ivs else current_iv
        interpretation = self.interpret_iv(iv_rank, iv_percentile)

        snapshot = IVSnapshot(
            symbol="NIFTY",
            current_iv=current_iv,
            iv_rank=round(iv_rank, 2),
            iv_percentile=round(iv_percentile, 2),
            iv_52w_high=round(iv_52w_high, 2),
            iv_52w_low=round(iv_52w_low, 2),
            as_of=datetime.utcnow(),
            interpretation=interpretation,
        )
        _cache_set(cache_key, snapshot)
        logger.info(
            "iv_rank.fetch_nifty_iv: done",
            current_iv=current_iv,
            iv_rank=iv_rank,
            interpretation=interpretation,
        )
        return snapshot

    async def fetch_pcr(
        self, client: httpx.AsyncClient, symbol: str = "NIFTY"
    ) -> PCRSnapshot:
        """Compute the Put-Call Ratio from the NSE option chain.

        PCR = total put OI / total call OI across all strikes + expiries.
        Cached for 3 minutes.
        """
        cache_key = f"pcr_{symbol}"
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug("iv_rank.fetch_pcr: cache hit", symbol=symbol)
            return cached  # type: ignore[return-value]

        url = _NSE_OPTION_CHAIN_URL.format(symbol=symbol)
        logger.info("iv_rank.fetch_pcr: fetching", url=url)

        resp = await client.get(url, headers=_NSE_HEADERS, timeout=15.0)
        resp.raise_for_status()
        payload = resp.json()

        data_rows = payload.get("records", {}).get("data", [])

        total_call_oi = 0
        total_put_oi = 0
        for row in data_rows:
            ce_data = row.get("CE", {})
            pe_data = row.get("PE", {})
            total_call_oi += int(ce_data.get("openInterest", 0) or 0)
            total_put_oi += int(pe_data.get("openInterest", 0) or 0)

        pcr = total_put_oi / total_call_oi if total_call_oi else 0.0

        if pcr > 1.2:
            signal: Literal["bullish", "bearish", "neutral"] = "bullish"
        elif pcr < 0.7:
            signal = "bearish"
        else:
            signal = "neutral"

        snapshot = PCRSnapshot(
            symbol=symbol,
            pcr=round(pcr, 4),
            call_oi=total_call_oi,
            put_oi=total_put_oi,
            as_of=datetime.utcnow(),
            signal=signal,
        )
        _cache_set(cache_key, snapshot)
        logger.info(
            "iv_rank.fetch_pcr: done",
            symbol=symbol,
            pcr=pcr,
            call_oi=total_call_oi,
            put_oi=total_put_oi,
            signal=signal,
        )
        return snapshot
