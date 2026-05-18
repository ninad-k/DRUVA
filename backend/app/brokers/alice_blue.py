"""AliceBlue ANT API adapter.

Reference: https://v2api.aliceblueonline.com/

AliceBlue uses ``Authorization: Bearer userId susertoken`` style header.
Best-effort REST mapping; verify against ANT staging before live use.
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


class AliceBlueAdapter(BrokerAdapter):
    broker_id = "alice_blue"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = "https://ant.aliceblueonline.com/rest/AliceBlueAPIService/api",
    ):
        self._http = http
        self._base_url = base_url
        self._user_id: str | None = None
        self._session: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        user_id = creds.extra.get("user_id") or creds.api_key
        session = creds.extra.get("session_token") or creds.extra.get("access_token")
        if not user_id or not session:
            raise BrokerError("alice_blue_authenticate_requires_user_id_and_session_token")
        self._user_id = str(user_id)
        self._session = str(session)
        return AuthSession(access_token=self._session, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._session:
            raise BrokerError("alice_blue_not_authenticated")
        return AuthSession(access_token=self._session, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = [
            {
                "complexty": "regular",
                "discqty": "0",
                "exch": req.exchange,
                "pCode": req.product,
                "prctyp": req.order_type,
                "price": str(float(req.price)) if req.price is not None else "0",
                "qty": str(int(req.quantity)),
                "ret": "DAY",
                "symbol_id": req.symbol,  # caller passes ANT instrument token
                "trading_symbol": req.tag or req.symbol,
                "transtype": req.side,
                "trigPrice": str(float(req.trigger_price)) if req.trigger_price is not None else "0",
            }
        ]
        response = await self._http.post(
            f"{self._base_url}/placeOrder/executePlaceOrder",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "place_order")
        first = (data or [{}])[0] if isinstance(data, list) else {}
        return OrderAck(
            broker_order_id=str(first.get("NOrdNo", first.get("nestOrderNumber", ""))),
            status=str(first.get("stat", "ok")),
        )

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body = {
            "nestOrderNumber": broker_order_id,
            "qty": str(int(req.quantity)) if req.quantity is not None else "0",
            "price": str(float(req.price)) if req.price is not None else "0",
            "trigPrice": str(float(req.trigger_price)) if req.trigger_price is not None else "0",
        }
        if req.order_type is not None:
            body["prctyp"] = req.order_type
        response = await self._http.post(
            f"{self._base_url}/placeOrder/modifyOrder", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        body = {"nestOrderNumber": broker_order_id}
        response = await self._http.post(
            f"{self._base_url}/placeOrder/cancelOrder", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        body = {"ret": "DAY"}
        response = await self._http.post(
            f"{self._base_url}/positionAndHoldings/positionBook",
            json=body,
            headers=self._headers(),
        )
        rows = await safe_json(response, self.broker_id, "positions")
        if not isinstance(rows, list):
            rows = rows.get("data", [])
        out: list[BrokerPosition] = []
        for item in rows or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("Tsym", ""),
                    exchange=item.get("Exchange", "NSE"),
                    quantity=Decimal(str(item.get("Netqty", 0))),
                    average_price=Decimal(str(item.get("NetAvgPrice", 0))),
                    last_price=Decimal(str(item.get("LTP", 0))),
                    pnl=Decimal(str(item.get("realisedprofitloss", 0))),
                    product=item.get("Pcode", "MIS"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(
            f"{self._base_url}/positionAndHoldings/holdings", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("HoldingVal", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("Symbol", ""),
                    exchange="NSE",
                    quantity=Decimal(str(item.get("HUqty", 0))),
                    average_price=Decimal(str(item.get("Price", 0))),
                    last_price=Decimal(str(item.get("LTP", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(
            f"{self._base_url}/limits/getRmsLimits", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "margin")
        first = (data or [{}])[0] if isinstance(data, list) else {}
        avail = Decimal(str(first.get("net", 0)))
        used = Decimal(str(first.get("debits", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        body = {"exch": exchange, "symbol": symbol}
        response = await self._http.post(
            f"{self._base_url}/marketWatch/scripDetails", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "quote")
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(data.get("LTP", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for s, e in symbols:
            out[(s, e)] = await self.get_quote(s, e)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        response = await self._http.get(
            f"{self._base_url}/marketData",
            params={"exch": exchange, "symbol": symbol, "type": "depth"},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "depth")
        # AliceBlue ANT returns depth under "DPR" or directly as bids/asks lists.
        raw = data if isinstance(data, dict) else {}

        def _levels(side: list[dict] | None) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("Price", lvl.get("price", 0)))),
                    quantity=Decimal(str(lvl.get("Quantity", lvl.get("quantity", 0)))),
                )
                for lvl in (side or [])[:5]
            ]

        return Depth(
            bids=_levels(raw.get("BidData", raw.get("bids", []))),
            asks=_levels(raw.get("AskData", raw.get("asks", []))),
        )

    async def get_history(
        self,
        symbol: str,
        exchange: str,  # noqa: ARG002
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        # AliceBlue ANT chart endpoint: GET /history
        response = await self._http.get(
            f"{self._base_url}/history",
            params={
                "symbol": symbol,
                "resolution": interval,
                "from": int(start.timestamp()),
                "to": int(end.timestamp()),
            },
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "history")
        out: list[Candle] = []
        # TradingView-style response: {t: [timestamps], o, h, l, c, v}
        times = data.get("t", []) or []
        opens = data.get("o", []) or []
        highs = data.get("h", []) or []
        lows = data.get("l", []) or []
        closes = data.get("c", []) or []
        volumes = data.get("v", []) or []
        for i, ts in enumerate(times):
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=datetime.fromtimestamp(int(ts)),
                    open=Decimal(str(opens[i] if i < len(opens) else 0)),
                    high=Decimal(str(highs[i] if i < len(highs) else 0)),
                    low=Decimal(str(lows[i] if i < len(lows) else 0)),
                    close=Decimal(str(closes[i] if i < len(closes) else 0)),
                    volume=Decimal(str(volumes[i] if i < len(volumes) else 0)),
                )
            )
        return out

    async def get_orderbook(self) -> list[BrokerOrder]:
        response = await self._http.get(
            f"{self._base_url}/placeOrder/orderBook", headers=self._headers()
        )
        rows = await safe_json(response, self.broker_id, "orderbook")
        if not isinstance(rows, list):
            rows = rows.get("data", [])
        out: list[BrokerOrder] = []
        for item in rows or []:
            out.append(
                BrokerOrder(
                    broker_order_id=str(item.get("Nstordno", item.get("nestOrderNumber", ""))),
                    symbol=item.get("Tsym", item.get("tradingSymbol", "")),
                    status=str(item.get("Status", item.get("status", ""))),
                    quantity=Decimal(str(item.get("Qty", item.get("qty", 0)))),
                    price=Decimal(str(item.get("Prc", item.get("price", 0)))) if item.get("Prc") or item.get("price") else None,
                )
            )
        return out

    async def get_tradebook(self) -> list[BrokerTrade]:
        response = await self._http.get(
            f"{self._base_url}/placeOrder/tradeBook", headers=self._headers()
        )
        rows = await safe_json(response, self.broker_id, "tradebook")
        if not isinstance(rows, list):
            rows = rows.get("data", [])
        out: list[BrokerTrade] = []
        for item in rows or []:
            raw_ts = item.get("Exchtm") or item.get("exchTime", "")
            try:
                traded_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                traded_at = utcnow()
            out.append(
                BrokerTrade(
                    broker_trade_id=str(item.get("Flordno", item.get("tradeId", ""))),
                    broker_order_id=str(item.get("Nstordno", item.get("nestOrderNumber", ""))),
                    symbol=item.get("Tsym", item.get("tradingSymbol", "")),
                    quantity=Decimal(str(item.get("Fillshares", item.get("qty", 0)))),
                    price=Decimal(str(item.get("Flprc", item.get("tradePrice", 0)))),
                    traded_at=traded_at,
                )
            )
        return out

    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[InstrumentMatch]:
        body = {"symbol": query, "exchange": [exchange or "NSE"]}
        response = await self._http.post(
            f"{self._base_url}/ScripDetails/getScripQuoteDetails",
            json=body,
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "search")
        out: list[InstrumentMatch] = []
        for item in data if isinstance(data, list) else []:
            out.append(
                InstrumentMatch(
                    symbol=item.get("trading_symbol", ""),
                    exchange=item.get("exch", "NSE"),
                    broker_token=str(item.get("token", "")),
                    instrument_type="EQ",
                )
            )
        return out

    async def health(self) -> BrokerHealth:
        return await health_probe(
            self._http,
            f"{self._base_url}/customer/accountDetails",
            self._headers(),
        )

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # AliceBlue publishes per-exchange CSVs at:
        # https://v2api.aliceblueonline.com/restpy/static/contract_master/{EXCHANGE}.csv
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
        if not self._user_id or not self._session:
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self._user_id} {self._session}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
