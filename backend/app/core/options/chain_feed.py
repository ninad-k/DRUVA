"""Live option chain feed from NSE (no auth required).

Fetches NIFTY/BANKNIFTY option chain every 3 minutes during market hours.
Provides: strikes, bid/ask, OI, IV, greeks for each contract.

NSE API endpoint used:
  https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY

The API returns the full chain for all expiries in one response. We filter
by the requested expiry (or select the nearest one in the 7-21 DTE window)
and compute all greeks using the existing Black-Scholes module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import AsyncGenerator, Literal

import httpx

from app.core.options.black_scholes import delta, gamma, greeks, implied_vol, theta, vega
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

# India time offset: UTC+5:30
_IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60

# NSE market hours (IST)
_MARKET_OPEN_H, _MARKET_OPEN_M = 9, 15
_MARKET_CLOSE_H, _MARKET_CLOSE_M = 15, 30

# Risk-free rate (RBI repo rate, decimal)
_RISK_FREE_RATE: float = 0.065
# NIFTY continuous dividend yield (approx, decimal)
_DIVIDEND_YIELD: float = 0.015

_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

_NSE_OPTION_CHAIN_URL = "https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"


@dataclass
class OptionContract:
    """A single options contract with market data and greeks."""

    symbol: str                        # e.g. "NIFTY24JAN25000CE"
    strike: float
    option_type: Literal["CE", "PE"]
    expiry: date
    last_price: float
    bid: float
    ask: float
    iv: float                          # annualised, decimal (e.g. 0.18 = 18%)
    oi: int                            # open interest in contracts
    volume: int
    delta: float
    theta: float                       # per calendar day
    gamma: float
    vega: float                        # per 1% vol move


@dataclass
class OptionChain:
    """Full chain for one symbol + expiry as fetched from NSE."""

    symbol: str
    spot: float
    atm_strike: float
    expiry: date
    contracts: list[OptionContract] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    total_call_oi: int = 0
    total_put_oi: int = 0
    pcr: float = 0.0


def _now_ist() -> datetime:
    """Return current time in IST (as offset-aware datetime)."""
    utc_now = datetime.now(timezone.utc)
    ist_offset = timezone(
        __import__("datetime").timedelta(seconds=_IST_OFFSET_SECONDS)
    )
    return utc_now.astimezone(ist_offset)


def _parse_expiry(expiry_str: str) -> date | None:
    """Parse NSE expiry strings like '26-Dec-2024' or '2024-12-26'."""
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(expiry_str, fmt).date()
        except ValueError:
            continue
    return None


class OptionChainFeed:
    """Thin async wrapper around the NSE option chain REST API.

    Creates a shared httpx session on first use; the caller should either
    call ``aclose()`` or use it as an async context manager.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=_NSE_HEADERS,
                follow_redirects=True,
                timeout=20.0,
            )
            # NSE requires a cookie from the main page before API calls work
            try:
                await self._client.get("https://www.nseindia.com/", timeout=10.0)
            except Exception as exc:  # noqa: BLE001
                logger.warning("chain_feed: failed to pre-warm NSE session", error=str(exc))
        return self._client

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> OptionChainFeed:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # ---------------------------------------------------------------- public

    async def fetch(self, symbol: str = "NIFTY", expiry: date | None = None) -> OptionChain:
        """Fetch the full option chain for ``symbol`` from NSE and return an
        :class:`OptionChain`.

        If ``expiry`` is ``None`` the method selects the nearest weekly expiry
        in the 7-21 DTE window (ideal for iron condors). If no such expiry
        exists the nearest overall expiry is used.
        """
        client = await self._get_client()
        url = _NSE_OPTION_CHAIN_URL.format(symbol=symbol)
        logger.info("chain_feed.fetch: GET", url=url, symbol=symbol, requested_expiry=str(expiry))

        resp = await client.get(url, headers=_NSE_HEADERS, timeout=20.0)
        resp.raise_for_status()
        payload = resp.json()

        records = payload.get("records", {})
        underlying_value: float = float(records.get("underlyingValue", 0) or 0)
        data_rows: list[dict] = records.get("data", [])

        # Collect all available expiry dates
        expiry_strings: set[str] = {row.get("expiryDate", "") for row in data_rows}
        available_expiries: list[date] = sorted(
            filter(None, (_parse_expiry(s) for s in expiry_strings))
        )

        today = date.today()

        if expiry is None:
            expiry = self.get_nearest_expiry(available_expiries) or (
                available_expiries[0] if available_expiries else today
            )

        # Compute T (years to expiry)
        dte = max((expiry - today).days, 0)
        T = dte / 365.0 if dte > 0 else 1 / 365.0

        # Filter rows for the selected expiry
        target_expiry_str: str | None = None
        for es in expiry_strings:
            parsed = _parse_expiry(es)
            if parsed == expiry:
                target_expiry_str = es
                break

        contracts: list[OptionContract] = []
        total_call_oi = 0
        total_put_oi = 0

        for row in data_rows:
            if row.get("expiryDate") != target_expiry_str:
                continue
            strike = float(row.get("strikePrice", 0))

            for opt_type in ("CE", "PE"):
                leg = row.get(opt_type, {})
                if not leg:
                    continue
                last_price = float(leg.get("lastPrice", 0) or 0)
                bid = float(leg.get("bidPrice", 0) or 0)
                ask = float(leg.get("askPrice", 0) or 0)
                oi = int(leg.get("openInterest", 0) or 0)
                vol = int(leg.get("totalTradedVolume", 0) or 0)
                nse_iv = float(leg.get("impliedVolatility", 0) or 0)

                # Compute or use NSE-provided IV (NSE IV is in %, convert to decimal)
                iv_decimal = nse_iv / 100.0 if nse_iv > 0 else 0.0
                if iv_decimal <= 0 and last_price > 0 and underlying_value > 0:
                    iv_decimal = implied_vol(
                        market_price=last_price,
                        S=underlying_value,
                        K=strike,
                        T=T,
                        r=_RISK_FREE_RATE,
                        option_type=opt_type,
                        q=_DIVIDEND_YIELD,
                    )
                    if iv_decimal != iv_decimal:  # NaN guard
                        iv_decimal = 0.0

                g = greeks(
                    S=underlying_value,
                    K=strike,
                    T=T,
                    r=_RISK_FREE_RATE,
                    sigma=max(iv_decimal, 1e-4),
                    option_type=opt_type,
                    q=_DIVIDEND_YIELD,
                )

                # NSE symbol convention: NIFTY + YYMMMSTRIKE + CE/PE
                expiry_tag = expiry.strftime("%y%b").upper()
                contract_symbol = f"{symbol}{expiry_tag}{int(strike)}{opt_type}"

                contract = OptionContract(
                    symbol=contract_symbol,
                    strike=strike,
                    option_type=opt_type,  # type: ignore[arg-type]
                    expiry=expiry,
                    last_price=last_price,
                    bid=bid,
                    ask=ask,
                    iv=iv_decimal,
                    oi=oi,
                    volume=vol,
                    delta=g.delta,
                    theta=g.theta,
                    gamma=g.gamma,
                    vega=g.vega,
                )
                contracts.append(contract)

                if opt_type == "CE":
                    total_call_oi += oi
                else:
                    total_put_oi += oi

        # Determine ATM strike
        atm_strike = underlying_value
        if underlying_value:
            strikes_seen = {c.strike for c in contracts}
            if strikes_seen:
                atm_strike = min(strikes_seen, key=lambda k: abs(k - underlying_value))

        pcr = total_put_oi / total_call_oi if total_call_oi else 0.0

        chain = OptionChain(
            symbol=symbol,
            spot=underlying_value,
            atm_strike=atm_strike,
            expiry=expiry,
            contracts=sorted(contracts, key=lambda c: (c.strike, c.option_type)),
            fetched_at=datetime.utcnow(),
            total_call_oi=total_call_oi,
            total_put_oi=total_put_oi,
            pcr=round(pcr, 4),
        )
        logger.info(
            "chain_feed.fetch: done",
            symbol=symbol,
            expiry=str(expiry),
            contracts=len(chain.contracts),
            spot=underlying_value,
            pcr=pcr,
        )
        return chain

    async def get_atm_contracts(
        self, chain: OptionChain, n_strikes: int = 5
    ) -> list[OptionContract]:
        """Return contracts for the n_strikes above and below ATM (both CE and PE).

        Total returned: up to 2 * (2*n_strikes + 1) contracts (CE+PE per strike).
        """
        atm = chain.atm_strike
        strikes_sorted = sorted({c.strike for c in chain.contracts})
        atm_index = min(range(len(strikes_sorted)), key=lambda i: abs(strikes_sorted[i] - atm))

        lo = max(0, atm_index - n_strikes)
        hi = min(len(strikes_sorted) - 1, atm_index + n_strikes)
        selected_strikes = set(strikes_sorted[lo : hi + 1])

        return [c for c in chain.contracts if c.strike in selected_strikes]

    def is_market_hours(self) -> bool:
        """Return True if the current IST time is within NSE trading hours (Mon–Fri, 09:15–15:30)."""
        now = _now_ist()
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        open_minutes = _MARKET_OPEN_H * 60 + _MARKET_OPEN_M
        close_minutes = _MARKET_CLOSE_H * 60 + _MARKET_CLOSE_M
        current_minutes = now.hour * 60 + now.minute
        return open_minutes <= current_minutes <= close_minutes

    async def start_polling(
        self, interval_seconds: int = 180
    ) -> AsyncGenerator[OptionChain, None]:
        """Async generator that yields a fresh :class:`OptionChain` every
        ``interval_seconds`` during market hours.

        Outside market hours the generator sleeps and checks again at the next
        interval. The caller is responsible for breaking out of the loop.
        """
        logger.info("chain_feed.start_polling: started", interval_seconds=interval_seconds)
        while True:
            if self.is_market_hours():
                try:
                    chain = await self.fetch()
                    yield chain
                except Exception as exc:  # noqa: BLE001
                    logger.warning("chain_feed.start_polling: fetch failed", error=str(exc))
            else:
                logger.debug("chain_feed.start_polling: outside market hours, sleeping")
            await asyncio.sleep(interval_seconds)

    def get_nearest_expiry(
        self,
        expiries: list[date],
        min_dte: int = 7,
        max_dte: int = 21,
    ) -> date | None:
        """Select the best expiry for an iron condor: 7–21 DTE, preferring
        the one closest to the middle of the range (≈14 DTE).

        Returns ``None`` if no expiry falls within the window.
        """
        today = date.today()
        candidates: list[tuple[int, date]] = []  # (dte, expiry)
        for exp in expiries:
            dte = (exp - today).days
            if min_dte <= dte <= max_dte:
                candidates.append((dte, exp))

        if not candidates:
            return None

        # Prefer the expiry closest to 14 DTE (sweet spot)
        target_dte = (min_dte + max_dte) // 2
        candidates.sort(key=lambda t: abs(t[0] - target_dte))
        return candidates[0][1]
