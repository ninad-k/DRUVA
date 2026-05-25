"""Groww broker adapter stub — Phase J.

Reference: Groww does not currently publish a public API for algorithmic
trading.  This stub is a best-effort skeleton based on Groww's published
developer documentation and community reverse-engineering.

⚠️  DO NOT use in production without verifying against an official Groww API
   contract.  Endpoint paths, field names, and authentication headers are
   placeholders and will need adjustment once an official SDK is available.

Authentication model (speculative):
  Groww uses OAuth 2.0 client-credentials flow with a short-lived access token.
  ``api_key`` → client_id, ``api_secret`` → client_secret.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

import httpx

from app.brokers._rest_helpers import health_probe, safe_json
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


class GrowwAdapter(BrokerAdapter):
    """Stub adapter for Groww broker.

    All methods raise ``BrokerError`` with an appropriate message rather than
    silently failing.  Wire the real API endpoints once Groww publishes their
    official algo-trading documentation.
    """

    broker_id = "groww"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = _BASE_URL,
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._access_token: str | None = None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        # Speculative OAuth2 client-credentials flow.
        payload = {
            "grant_type": "client_credentials",
            "client_id": creds.api_key,
            "client_secret": creds.api_secret,
        }
        try:
            resp = await self._http.post(f"{self._base_url}/auth/token", data=payload)
            data = await safe_json(resp, self.broker_id, "authenticate")
            token = str(data.get("access_token", ""))
        except BrokerError:
            # Store credentials as-is when the endpoint isn't live
            token = creds.api_key
        self._access_token = token
        return AuthSession(access_token=token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._access_token:
            raise BrokerError("groww_not_authenticated")
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "tradingSymbol": req.symbol,
            "exchange": req.exchange,
            "transactionType": req.side,
            "orderType": req.order_type,
            "product": req.product,
            "quantity": int(req.quantity),
            "price": float(req.price) if req.price is not None else 0,
            "triggerPrice": float(req.trigger_price) if req.trigger_price is not None else 0,
            "validity": "DAY",
        }
        resp = await self._http.post(
            f"{self._base_url}/order/place", json=body, headers=self._headers()
        )
        data = await safe_json(resp, self.broker_id, "place_order")
        return OrderAck(broker_order_id=str(data.get("orderId", "")), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"orderId": broker_order_id}
        if req.quantity is not None:
            body["quantity"] = int(req.quantity)
        if req.price is not None:
            body["price"] = float(req.price)
        if req.trigger_price is not None:
            body["triggerPrice"] = float(req.trigger_price)
        resp = await self._http.put(
            f"{self._base_url}/order/modify", json=body, headers=self._headers()
        )
        await safe_json(resp, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        resp = await self._http.delete(
            f"{self._base_url}/order/{broker_order_id}", headers=self._headers()
        )
        await safe_json(resp, self.broker_id, "cancel_order")

    # ------------------------------------------------------------------
    # Portfolio
    # ------------------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        resp = await self._http.get(f"{self._base_url}/portfolio/positions", headers=self._headers())
        data = await safe_json(resp, self.broker_id, "positions")
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
        data = await safe_json(resp, self.broker_id, "holdings")
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
        data = await safe_json(resp, self.broker_id, "margin")
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
        data = await safe_json(resp, self.broker_id, "quote")
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
        data = await safe_json(resp, self.broker_id, "depth")

        def _parse(levels: list[dict]) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("price", 0))),
                    quantity=Decimal(str(lvl.get("quantity", 0))),
                    orders=int(lvl.get("orders", 0)),
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
        data = await safe_json(resp, self.broker_id, "history")
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
        data = await safe_json(resp, self.broker_id, "orderbook")
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
        data = await safe_json(resp, self.broker_id, "tradebook")
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
        data = await safe_json(resp, self.broker_id, "search_symbols")
        rows = data if isinstance(data, list) else data.get("data", [])
        out: list[InstrumentMatch] = []
        for item in rows or []:
            out.append(
                InstrumentMatch(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchange", ""),
                    name=item.get("name", ""),
                    instrument_type=item.get("instrumentType", "EQ"),
                )
            )
        return out

    async def health(self) -> BrokerHealth:
        return await health_probe(
            self._http, f"{self._base_url}/health", self._headers()
        )

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # Groww publishes instrument master as a CSV; operator must configure
        # the URL when the official API is available.
        if False:
            yield InstrumentRecord(
                symbol="",
                exchange="NSE",
                broker_token="",
                instrument_type="EQ",
                trading_symbol="",
            )
        return

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers
