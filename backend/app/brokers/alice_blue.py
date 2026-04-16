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

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: alice_blue depth")

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:  # noqa: ARG002
        raise NotImplementedError("TODO: alice_blue history (use chart endpoint)")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: alice_blue orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: alice_blue tradebook")

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
