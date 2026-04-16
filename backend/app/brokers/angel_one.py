"""Angel One SmartAPI adapter.

Reference: https://smartapi.angelbroking.com/docs

Angel uses JWT tokens (`Authorization: Bearer <jwt>`) plus several extra
headers (`X-PrivateKey`, `X-ClientLocalIP`, …). Best-effort implementation;
verify against SmartAPI sandbox before live use.
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

_PRODUCT = {"MIS": "INTRADAY", "CNC": "DELIVERY", "NRML": "CARRYFORWARD"}


class AngelOneAdapter(BrokerAdapter):
    broker_id = "angel_one"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = "https://apiconnect.angelbroking.com",
    ):
        self._http = http
        self._base_url = base_url
        self._jwt: str | None = None
        self._api_key: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        token = creds.extra.get("jwt") or creds.extra.get("access_token")
        if not token:
            raise BrokerError("angel_one_authenticate_requires_jwt_in_extra")
        self._jwt = str(token)
        self._api_key = creds.api_key
        return AuthSession(access_token=self._jwt, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._jwt:
            raise BrokerError("angel_one_not_authenticated")
        return AuthSession(access_token=self._jwt, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "variety": "NORMAL",
            "tradingsymbol": req.symbol,
            "symboltoken": req.tag or "",  # caller passes Angel's symboltoken
            "transactiontype": req.side,
            "exchange": req.exchange,
            "ordertype": req.order_type,
            "producttype": _PRODUCT.get(req.product, "INTRADAY"),
            "duration": "DAY",
            "price": str(float(req.price)) if req.price is not None else "0",
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(int(req.quantity)),
        }
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/placeOrder",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "place_order")
        return OrderAck(broker_order_id=str(data.get("data", {}).get("orderid", "")), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"variety": "NORMAL", "orderid": broker_order_id}
        if req.quantity is not None:
            body["quantity"] = str(int(req.quantity))
        if req.price is not None:
            body["price"] = str(float(req.price))
        if req.order_type is not None:
            body["ordertype"] = req.order_type
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/modifyOrder",
            json=body,
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        body = {"variety": "NORMAL", "orderid": broker_order_id}
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/cancelOrder",
            json=body,
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/getPosition",
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "positions")
        out: list[BrokerPosition] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("tradingsymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("netqty", 0))),
                    average_price=Decimal(str(item.get("avgnetprice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                    pnl=Decimal(str(item.get("pnl", 0))),
                    product=item.get("producttype", "INTRADAY"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(
            f"{self._base_url}/rest/secure/angelbroking/portfolio/v1/getHolding",
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("tradingsymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("averageprice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(
            f"{self._base_url}/rest/secure/angelbroking/user/v1/getRMS",
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "margin")
        d = data.get("data", {})
        avail = Decimal(str(d.get("availablecash", 0)))
        used = Decimal(str(d.get("utilisedmargin", d.get("net", 0))))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        body = {"mode": "LTP", "exchangeTokens": {exchange: [symbol]}}
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/market/v1/quote",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "quote")
        rows = data.get("data", {}).get("fetched", []) or []
        first = rows[0] if rows else {}
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(first.get("ltp", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for s, e in symbols:
            out[(s, e)] = await self.get_quote(s, e)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: angel_one depth (mode=FULL on quote endpoint)")

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        body = {
            "exchange": exchange,
            "symboltoken": symbol,
            "interval": {
                "1m": "ONE_MINUTE",
                "5m": "FIVE_MINUTE",
                "15m": "FIFTEEN_MINUTE",
                "1h": "ONE_HOUR",
                "1d": "ONE_DAY",
            }.get(interval, "ONE_DAY"),
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        }
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/historical/v1/getCandleData",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "history")
        out: list[Candle] = []
        for row in data.get("data", []) or []:
            ts, o, h, l, c, v = row
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=datetime.fromisoformat(str(ts).replace("Z", "+00:00")),
                    open=Decimal(str(o)),
                    high=Decimal(str(h)),
                    low=Decimal(str(l)),
                    close=Decimal(str(c)),
                    volume=Decimal(str(v)),
                )
            )
        return out

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: angel_one orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: angel_one tradebook")

    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[InstrumentMatch]:
        body = {"exchange": exchange or "NSE", "searchscrip": query}
        response = await self._http.post(
            f"{self._base_url}/rest/secure/angelbroking/order/v1/searchScrip",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "search_symbols")
        out: list[InstrumentMatch] = []
        for item in data.get("data", []) or []:
            out.append(
                InstrumentMatch(
                    symbol=item.get("tradingsymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    broker_token=item.get("symboltoken", ""),
                    instrument_type="EQ",
                )
            )
        return out

    async def health(self) -> BrokerHealth:
        return await health_probe(
            self._http,
            f"{self._base_url}/rest/secure/angelbroking/user/v1/getProfile",
            self._headers(),
        )

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # Angel publishes a single big JSON of all instruments at:
        # https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json
        if False:
            yield InstrumentRecord(
                symbol="",
                exchange="NSE",
                broker_token="",
                instrument_type="EQ",
                trading_symbol="",
            )
        return

    def _headers(self) -> dict[str, str]:
        if not self._jwt or not self._api_key:
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self._jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": self._api_key,
        }
