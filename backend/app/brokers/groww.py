"""Groww Trade API adapter.

Reference: https://groww.in/trade-api/docs/curl

Verified against the public docs: access-token endpoint (``POST
/token/api/access``), ``POST /order/create`` request fields, the
``{"status", "payload", "error"}`` response envelope, the ``X-API-VERSION``
header and the instrument CSV URL/columns. The base host is also
unverified (kept from the skeleton).

NOT verified (paths taken from the pre-existing skeleton; the docs name the
operations but do not publish REST paths): order modify/cancel/list/trades,
positions, holdings, margin, quote, depth, history and search. Re-check each
against the sandbox before live use.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal

import httpx

from app.brokers._rest_helpers import health_probe, iter_csv_rows, safe_json
from app.brokers.base import (
    AuthSession,
    BrokerAdapter,
    BrokerCredentials,
    BrokerHealth,
    BrokerHolding,
    BrokerOrder,
    BrokerPosition,
    BrokerTrade,
    Depth,
    DepthLevel,
    InstrumentMatch,
    InstrumentRecord,
    MarginDetails,
    OrderAck,
    OrderModifyRequest,
    OrderRequest,
    Quote,
)
from app.core.errors import BrokerError
from app.strategies.base import Candle
from app.utils.time import utcnow

_BASE_URL = "https://growwapi.groww.in/v1"
INSTRUMENT_URL = "https://growwapi-assets.groww.in/instruments/instrument.csv"

_SEGMENT_BY_EXCHANGE = {"NSE": "CASH", "BSE": "CASH", "NFO": "FNO", "BFO": "FNO"}


class GrowwAdapter(BrokerAdapter):
    """Adapter for the Groww Trade API (see module docstring for what is verified)."""

    broker_id = "groww"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = _BASE_URL,
        instrument_url: str = INSTRUMENT_URL,
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._instrument_url = instrument_url
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        """Exchange API key + secret for an access token.

        ``api_key`` is the Bearer API key; ``api_secret`` is only used to
        sign the request. If ``creds.extra['totp']`` is set the TOTP flow is
        used instead (the secret is then not needed).
        """
        totp = creds.extra.get("totp")
        if totp:
            body = {"key_type": "totp", "totp": str(totp)}
        else:
            # Checksum = sha256(secret + timestamp) per the Groww SDK; the
            # REST docs only say "SHA256_HASH" (formula unverified).
            ts = str(int(time.time()))
            checksum = hashlib.sha256((creds.api_secret + ts).encode()).hexdigest()
            body = {"key_type": "approval", "checksum": checksum, "timestamp": ts}
        resp = await self._http.post(
            f"{self._base_url}/token/api/access",
            json=body,
            headers={
                "Authorization": f"Bearer {creds.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-API-VERSION": "1.0",
            },
        )
        data = await self._json(resp, "authenticate")
        token = str(data.get("token", "")) if isinstance(data, dict) else ""
        if not token:
            raise BrokerError("groww_authenticate_no_token")
        expires_at = None
        raw_exp = data.get("expiry")
        if raw_exp:
            try:
                expires_at = datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00"))
            except ValueError:
                expires_at = None
        self._access_token = token
        return AuthSession(access_token=token, refresh_token=None, expires_at=expires_at)

    async def refresh_token(self) -> AuthSession:
        if not self._access_token:
            raise BrokerError("groww_not_authenticated")
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body: dict = {
            "trading_symbol": req.symbol,
            "exchange": req.exchange,
            "segment": _segment(req.exchange),
            "transaction_type": req.side,
            "order_type": req.order_type,
            "product": req.product,
            "quantity": int(req.quantity),
            "price": float(req.price) if req.price is not None else 0,
            "trigger_price": float(req.trigger_price) if req.trigger_price is not None else 0,
            "validity": "DAY",
        }
        if req.tag:
            body["order_reference_id"] = req.tag
        resp = await self._http.post(
            f"{self._base_url}/order/create", json=body, headers=self._headers()
        )
        data = await self._json(resp, "place_order")
        return OrderAck(
            broker_order_id=str(data.get("groww_order_id", "")),
            status=str(data.get("order_status", "accepted")).lower(),
            message=str(data.get("remark", "") or ""),
        )

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        # Groww requires quantity, order_type and segment on modify. The base
        # request cannot carry segment, so CASH is assumed (F&O unsupported).
        body: dict = {"groww_order_id": broker_order_id, "segment": "CASH"}
        if req.quantity is not None:
            body["quantity"] = int(req.quantity)
        if req.price is not None:
            body["price"] = float(req.price)
        if req.trigger_price is not None:
            body["trigger_price"] = float(req.trigger_price)
        if req.order_type is not None:
            body["order_type"] = req.order_type
        resp = await self._http.post(
            f"{self._base_url}/order/modify", json=body, headers=self._headers()
        )
        await self._json(resp, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        resp = await self._http.post(
            f"{self._base_url}/order/cancel",
            json={"groww_order_id": broker_order_id, "segment": "CASH"},
            headers=self._headers(),
        )
        await self._json(resp, "cancel_order")

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        resp = await self._http.get(f"{self._base_url}/portfolio/positions", headers=self._headers())
        data = await self._json(resp, "positions")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[BrokerPosition] = []
        for item in rows or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("netQty", 0))),
                    average_price=Decimal(str(item.get("avgPrice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                    pnl=Decimal(str(item.get("pnl", 0))),
                    product=item.get("product", "MIS"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        resp = await self._http.get(f"{self._base_url}/portfolio/holdings", headers=self._headers())
        data = await self._json(resp, "holdings")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[BrokerHolding] = []
        for item in rows or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("avgPrice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        resp = await self._http.get(f"{self._base_url}/user/funds", headers=self._headers())
        data = await self._json(resp, "margin")
        avail = Decimal(str(data.get("availableAmount", data.get("available", 0))))
        used = Decimal(str(data.get("utilizedAmount", data.get("used", 0))))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        resp = await self._http.get(
            f"{self._base_url}/marketdata/quote",
            params={"symbol": symbol, "exchange": exchange},
            headers=self._headers(),
        )
        data = await self._json(resp, "quote")
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(data.get("ltp", data.get("lastPrice", 0)))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for sym, exc in symbols:
            out[(sym, exc)] = await self.get_quote(sym, exc)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        resp = await self._http.get(
            f"{self._base_url}/marketdata/depth",
            params={"symbol": symbol, "exchange": exchange},
            headers=self._headers(),
        )
        data = await self._json(resp, "depth")

        def _parse(levels: list[dict]) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("price", 0))),
                    quantity=Decimal(str(lvl.get("quantity", 0))),
                )
                for lvl in levels[:5]
            ]

        return Depth(
            bids=_parse(data.get("bids", [])),
            asks=_parse(data.get("asks", data.get("offers", []))),
        )

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        params = {
            "symbol": symbol,
            "exchange": exchange,
            "interval": interval,
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
        resp = await self._http.get(
            f"{self._base_url}/marketdata/history", params=params, headers=self._headers()
        )
        data = await self._json(resp, "history")
        candles_raw = data if isinstance(data, list) else data.get("candles", [])
        out: list[Candle] = []
        for c in candles_raw or []:
            if isinstance(c, (list, tuple)) and len(c) >= 6:
                ts_val, o, h, l, cl, vol = c[0], c[1], c[2], c[3], c[4], c[5]
            elif isinstance(c, dict):
                ts_val = c.get("timestamp", c.get("ts", 0))
                o, h, l, cl, vol = (
                    c.get("open", 0), c.get("high", 0), c.get("low", 0),
                    c.get("close", 0), c.get("volume", 0),
                )
            else:
                continue
            ts = datetime.fromtimestamp(int(ts_val)) if isinstance(ts_val, (int, float)) else datetime.fromisoformat(str(ts_val))
            out.append(Candle(symbol=symbol, timeframe=interval, ts=ts,
                              open=Decimal(str(o)), high=Decimal(str(h)),
                              low=Decimal(str(l)), close=Decimal(str(cl)),
                              volume=Decimal(str(vol))))
        return out

    # ------------------------------------------------------------------
    # Order/trade book
    # ------------------------------------------------------------------

    async def get_orderbook(self) -> list[BrokerOrder]:
        resp = await self._http.get(f"{self._base_url}/order/list", headers=self._headers())
        data = await self._json(resp, "orderbook")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[BrokerOrder] = []
        for item in rows or []:
            out.append(
                BrokerOrder(
                    broker_order_id=str(item.get("orderId", "")),
                    symbol=item.get("tradingSymbol", ""),
                    status=str(item.get("status", "")),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    price=Decimal(str(item.get("price", 0))) if item.get("price") else None,
                )
            )
        return out

    async def get_tradebook(self) -> list[BrokerTrade]:
        resp = await self._http.get(f"{self._base_url}/order/trades", headers=self._headers())
        data = await self._json(resp, "tradebook")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[BrokerTrade] = []
        for item in rows or []:
            raw_ts = item.get("tradeTimestamp", item.get("time", ""))
            try:
                traded_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                traded_at = utcnow()
            out.append(
                BrokerTrade(
                    broker_trade_id=str(item.get("tradeId", "")),
                    broker_order_id=str(item.get("orderId", "")),
                    symbol=item.get("tradingSymbol", ""),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    price=Decimal(str(item.get("tradePrice", item.get("price", 0)))),
                    traded_at=traded_at,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[InstrumentMatch]:
        params: dict = {"q": query}
        if exchange:
            params["exchange"] = exchange
        resp = await self._http.get(
            f"{self._base_url}/marketdata/search", params=params, headers=self._headers()
        )
        data = await self._json(resp, "search_symbols")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[InstrumentMatch] = []
        for item in rows or []:
            out.append(
                InstrumentMatch(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchange", ""),
                    trading_symbol=item.get("tradingSymbol", ""),
                    instrument_type=item.get("instrumentType", "EQ"),
                )
            )
        return out

    async def health(self) -> BrokerHealth:
        return await health_probe(
            self._http, f"{self._base_url}/health", self._headers()
        )

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        async for row in iter_csv_rows(
            self._http, self._instrument_url, self.broker_id, "instruments"
        ):
            record = _groww_instrument(row)
            if record is not None:
                yield record

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-API-VERSION": "1.0",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _json(self, resp: httpx.Response, op: str):
        """Parse the response and unwrap Groww's status/payload envelope."""
        data = await safe_json(resp, self.broker_id, op)
        if not isinstance(data, dict):
            return data
        if data.get("status") == "FAILURE":
            err = data.get("error") or {}
            raise BrokerError(
                f"groww_{op}_failed:{err.get('code', '')}:{str(err.get('message', ''))[:200]}"
            )
        if "payload" in data:
            return data["payload"]
        return data


def _segment(exchange: str) -> str:
    try:
        return _SEGMENT_BY_EXCHANGE[exchange]
    except KeyError:
        raise BrokerError(f"groww_unsupported_exchange:{exchange}") from None


def _groww_instrument(row: dict[str, str]) -> InstrumentRecord | None:
    exchange = row.get("exchange", "")
    trading_symbol = row.get("trading_symbol", "")
    token = row.get("exchange_token", "")
    if not (exchange and trading_symbol and token):
        return None
    if row.get("segment") == "FNO":
        exchange = {"NSE": "NFO", "BSE": "BFO"}.get(exchange, exchange)
    expiry = None
    raw_exp = row.get("expiry_date", "")
    if raw_exp:
        try:
            expiry = date.fromisoformat(raw_exp[:10])
        except ValueError:
            expiry = None
    strike = None
    try:
        sv = Decimal(row.get("strike_price") or "0")
        strike = sv if sv > 0 else None
    except ArithmeticError:
        strike = None
    try:
        lot = int(Decimal(row.get("lot_size") or "1"))
    except ArithmeticError:
        lot = 1
    try:
        tick = Decimal(row.get("tick_size") or "0")
    except ArithmeticError:
        tick = Decimal(0)
    if tick <= 0:
        tick = Decimal("0.05")
    return InstrumentRecord(
        symbol=trading_symbol,
        exchange=exchange,
        broker_token=token,
        instrument_type=row.get("instrument_type") or "EQ",
        trading_symbol=trading_symbol,
        lot_size=max(lot, 1),
        tick_size=tick,
        expiry=expiry,
        strike=strike,
        isin=row.get("isin") or None,
        exchange_token=token,
        extra={
            k: v
            for k, v in (
                ("groww_symbol", row.get("groww_symbol", "")),
                ("segment", row.get("segment", "")),
                ("buy_allowed", row.get("buy_allowed", "")),
                ("sell_allowed", row.get("sell_allowed", "")),
            )
            if v
        },
    )
