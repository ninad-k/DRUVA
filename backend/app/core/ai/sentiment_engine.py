"""Market sentiment engine for Indian markets.

Aggregates multiple sentiment signals into a composite score:
  1. India VIX (fear gauge)
  2. FII/DII net activity (from NSE daily data)
  3. Put-Call Ratio (NSE options data)
  4. NIFTY advance/decline ratio
  5. Regime signal from HMM (Crash/Bear/Neutral/Bull/Euphoria)

Composite score: -100 (extreme fear) to +100 (extreme greed)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.core.market.india_vix import NSE_HEADERS, get_vix_with_fallback
from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# NSE endpoint constants
# ---------------------------------------------------------------------------

NSE_FII_DII_URL = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices"

# Module-level result cache
_cache: dict[str, Any] = {}
_CACHE_TTL = timedelta(minutes=15)

# Regime label ordering
_REGIME_SCORES: dict[str, float] = {
    "Crash": -100.0,
    "Bear": -50.0,
    "Neutral": 0.0,
    "Bull": 50.0,
    "Euphoria": 75.0,
}

_DEFAULT_WEIGHTS: dict[str, float] = {
    "vix": 0.25,
    "pcr": 0.20,
    "fii": 0.25,
    "regime": 0.20,
    "adv_dec": 0.10,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SentimentReading:
    """A composite market-sentiment snapshot."""

    score: float
    """Composite score in [-100, +100]. Negative = fear, positive = greed."""

    label: str
    """Human-readable label: Extreme Fear / Fear / Neutral / Greed / Extreme Greed."""

    vix: float
    """India VIX level at the time of the reading."""

    pcr: float
    """NIFTY Put-Call Ratio (OI-weighted) at the time of the reading."""

    fii_net_cr: float
    """FII net buying (positive) or selling (negative) in crore INR for the day."""

    dii_net_cr: float
    """DII net buying (positive) or selling (negative) in crore INR for the day."""

    advance_decline: float
    """Advance / (Advance + Decline) ratio for NIFTY 50 constituents [0, 1]."""

    regime: str
    """Current market regime label fed from the HMM model."""

    signals: dict[str, float] = field(default_factory=dict)
    """Individual sub-scores before weighting, keyed by signal name."""

    as_of: datetime = field(default_factory=utcnow)
    """UTC timestamp of the reading."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SentimentEngine:
    """Aggregates multiple market signals into a single sentiment score.

    Usage::

        async with httpx.AsyncClient() as client:
            engine = SentimentEngine()
            reading = await engine.compute(client, current_regime="Bull")
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def compute(
        self,
        client: httpx.AsyncClient,
        current_regime: str = "Neutral",
    ) -> SentimentReading:
        """Fetch all live signals and return a composite SentimentReading.

        Results are cached for 15 minutes to avoid hammering NSE endpoints.
        The regime signal is always taken from the caller (it comes from the
        live HMM model, not a network fetch).
        """
        now = utcnow()
        cached_at: datetime | None = _cache.get("fetched_at")
        if (
            cached_at is not None
            and (now - cached_at) < _CACHE_TTL
            and _cache.get("regime") == current_regime
        ):
            logger.debug("sentiment_engine.cache_hit")
            return _cache["reading"]  # type: ignore[return-value]

        logger.info("sentiment_engine.compute_start", regime=current_regime)

        # ---- fetch live data (with per-call error tolerance) ---------------
        vix_reading = await get_vix_with_fallback(client)
        vix = vix_reading.value

        try:
            fii_net, dii_net = await self._fetch_fii_dii(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment_engine.fii_dii_failed", error=str(exc))
            fii_net, dii_net = 0.0, 0.0

        try:
            adv_dec = await self._fetch_advance_decline(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment_engine.adv_dec_failed", error=str(exc))
            adv_dec = 0.5  # neutral fallback

        # PCR: attempt from the NSE option chain summary; use fallback on error
        try:
            pcr = await self._fetch_pcr(client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment_engine.pcr_failed", error=str(exc))
            pcr = 1.0  # neutral fallback

        # ---- individual signal scores ---------------------------------------
        signals: dict[str, float] = {
            "vix": self._compute_vix_score(vix),
            "pcr": self._compute_pcr_score(pcr),
            "fii": self._compute_fii_score(fii_net),
            "regime": self._compute_regime_score(current_regime),
            "adv_dec": self._compute_adv_dec_score(adv_dec),
        }

        # ---- composite weighted average ------------------------------------
        composite = self._composite(signals, _DEFAULT_WEIGHTS)
        label = self.label_score(composite)

        reading = SentimentReading(
            score=composite,
            label=label,
            vix=vix,
            pcr=pcr,
            fii_net_cr=fii_net,
            dii_net_cr=dii_net,
            advance_decline=adv_dec,
            regime=current_regime,
            signals=signals,
            as_of=now,
        )

        _cache["reading"] = reading
        _cache["fetched_at"] = now
        _cache["regime"] = current_regime

        logger.info(
            "sentiment_engine.computed",
            score=round(composite, 2),
            label=label,
            vix=vix,
            pcr=pcr,
            fii_net_cr=fii_net,
            adv_dec=round(adv_dec, 3),
        )
        return reading

    # ------------------------------------------------------------------
    # Network fetchers
    # ------------------------------------------------------------------

    async def _fetch_fii_dii(self, client: httpx.AsyncClient) -> tuple[float, float]:
        """Fetch today's FII and DII net buy/sell activity from NSE.

        Returns (fii_net_crore, dii_net_crore).
        Positive values indicate net buying; negative indicate net selling.

        NSE returns a list of entries per date; we use the most recent entry.
        """
        resp = await client.get(
            NSE_FII_DII_URL,
            headers=NSE_HEADERS,
            timeout=15.0,
        )
        resp.raise_for_status()
        payload: list[dict[str, Any]] = resp.json()

        if not payload:
            raise ValueError("Empty FII/DII response from NSE")

        # The first entry is the latest date
        latest = payload[0]
        fii_net = _parse_crore(latest.get("fiiBuySell") or latest.get("netFII") or latest.get("fiiNetBuy", "0"))
        dii_net = _parse_crore(latest.get("diiBuySell") or latest.get("netDII") or latest.get("diiNetBuy", "0"))

        logger.debug("sentiment_engine.fii_dii", fii_net_cr=fii_net, dii_net_cr=dii_net)
        return fii_net, dii_net

    async def _fetch_advance_decline(self, client: httpx.AsyncClient) -> float:
        """Compute advance/decline ratio for NIFTY 50 from NSE allIndices.

        Returns advances / (advances + declines) in [0, 1].
        Falls back to 0.5 (neutral) if the index or fields are absent.
        """
        resp = await client.get(
            NSE_ALL_INDICES_URL,
            headers=NSE_HEADERS,
            timeout=15.0,
        )
        resp.raise_for_status()
        payload = resp.json()

        records: list[dict[str, Any]] = payload.get("data", [])
        for rec in records:
            symbol = rec.get("indexSymbol", "").upper()
            if symbol == "NIFTY 50":
                advances = float(rec.get("advances", 0) or 0)
                declines = float(rec.get("declines", 0) or 0)
                total = advances + declines
                if total == 0:
                    return 0.5
                ratio = advances / total
                logger.debug(
                    "sentiment_engine.adv_dec",
                    advances=advances,
                    declines=declines,
                    ratio=round(ratio, 3),
                )
                return ratio

        # NIFTY 50 not found; return neutral
        logger.warning("sentiment_engine.nifty50_not_found_in_allIndices")
        return 0.5

    async def _fetch_pcr(self, client: httpx.AsyncClient) -> float:
        """Fetch the NIFTY put-call ratio from the NSE option chain summary.

        The option chain endpoint exposes the total OI for CE and PE across
        all strikes; PCR = total PE OI / total CE OI.
        Falls back to 1.0 on error.
        """
        url = "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY"
        resp = await client.get(url, headers=NSE_HEADERS, timeout=20.0)
        resp.raise_for_status()
        payload = resp.json()

        filtered: list[dict[str, Any]] = payload.get("filtered", {}).get("data", [])
        total_ce_oi = sum(float(r.get("CE", {}).get("openInterest", 0) or 0) for r in filtered)
        total_pe_oi = sum(float(r.get("PE", {}).get("openInterest", 0) or 0) for r in filtered)

        if total_ce_oi == 0:
            return 1.0
        pcr = total_pe_oi / total_ce_oi
        logger.debug("sentiment_engine.pcr", pcr=round(pcr, 3), ce_oi=total_ce_oi, pe_oi=total_pe_oi)
        return pcr

    # ------------------------------------------------------------------
    # Signal scorers
    # ------------------------------------------------------------------

    def _compute_vix_score(self, vix: float) -> float:
        """Map India VIX to a sentiment sub-score.

        Calibration:
          VIX 10  → +50 (very low fear, greedish)
          VIX 16  →   0 (neutral)
          VIX 25  → -50 (elevated fear)
          VIX 35  → -100 (panic)

        Uses two linear segments: [10, 16] → [+50, 0] and [16, 35] → [0, -100].
        Clamped to [-100, +50].
        """
        if vix <= 10.0:
            return 50.0
        if vix <= 16.0:
            # Linear: 10→+50, 16→0
            return 50.0 - (vix - 10.0) * (50.0 / 6.0)
        if vix <= 35.0:
            # Linear: 16→0, 35→-100
            return -(vix - 16.0) * (100.0 / 19.0)
        return -100.0

    def _compute_pcr_score(self, pcr: float) -> float:
        """Map Put-Call Ratio to a contrarian sentiment score.

        Contrarian interpretation:
          PCR 1.5  → +50 (heavy put buying = bearish crowd → contrarian bullish)
          PCR 1.0  →   0 (neutral)
          PCR 0.7  → -50 (heavy call buying = bullish crowd → contrarian bearish)

        Two linear segments. Clamped to [-75, +75].
        """
        if pcr >= 1.5:
            # Linear: 1.5→+50, 2.0→+75 (cap)
            excess = min(pcr - 1.5, 0.5)
            return 50.0 + excess * 50.0
        if pcr >= 1.0:
            # Linear: 1.0→0, 1.5→+50
            return (pcr - 1.0) * (50.0 / 0.5)
        # Linear: 0.7→-50, 1.0→0
        if pcr >= 0.7:
            return (pcr - 1.0) * (50.0 / 0.3)
        return -75.0

    def _compute_fii_score(self, fii_net: float) -> float:
        """Map FII net buy/sell activity to a sentiment sub-score.

        Normalization: ±5000 crore maps to ±50 points.
        Clamped to [-100, +100].
        """
        raw = (fii_net / 5000.0) * 50.0
        return max(-100.0, min(100.0, raw))

    def _compute_regime_score(self, regime: str) -> float:
        """Map a regime label to a fixed sentiment score.

        Crash=-100, Bear=-50, Neutral=0, Bull=+50, Euphoria=+75.
        Unknown regimes default to 0.
        """
        return _REGIME_SCORES.get(regime, 0.0)

    def _compute_adv_dec_score(self, adv_dec_ratio: float) -> float:
        """Map advance/decline ratio to a sentiment sub-score.

        adv_dec_ratio is in [0, 1].
          1.0 (all advances)  → +100
          0.5 (neutral)       →    0
          0.0 (all declines)  → -100
        """
        return (adv_dec_ratio - 0.5) * 200.0

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def _composite(
        self,
        scores: dict[str, float],
        weights: dict[str, float],
    ) -> float:
        """Compute a weighted average of signal scores.

        Missing signals are skipped; weights are renormalized to sum to 1.
        Returns a value in [-100, +100].
        """
        total_weight = 0.0
        weighted_sum = 0.0
        for name, weight in weights.items():
            score = scores.get(name)
            if score is None:
                continue
            weighted_sum += weight * score
            total_weight += weight

        if total_weight == 0.0:
            return 0.0

        composite = weighted_sum / total_weight
        return max(-100.0, min(100.0, composite))

    # ------------------------------------------------------------------
    # Labeling
    # ------------------------------------------------------------------

    def label_score(self, score: float) -> str:
        """Convert a composite score to a human-readable label.

        Thresholds:
          score ≤ -60  → Extreme Fear
          score ≤ -20  → Fear
          score ≤ +20  → Neutral
          score ≤ +60  → Greed
          score  > +60 → Extreme Greed
        """
        if score <= -60.0:
            return "Extreme Fear"
        if score <= -20.0:
            return "Fear"
        if score <= 20.0:
            return "Neutral"
        if score <= 60.0:
            return "Greed"
        return "Extreme Greed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_crore(value: Any) -> float:
    """Parse a crore string or number that may contain commas or parentheses."""
    if value is None:
        return 0.0
    text = str(value).replace(",", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(text)
    except (ValueError, TypeError):
        return 0.0
