"""5paisa OpenAPI adapter.

Reference: https://www.5paisa.com/developerapi

Best-effort REST mapping. 5paisa's API is XML-flavoured JSON with PascalCase
field names. Verify against their staging endpoints before live use.
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


class FivePaisaAdapter(BrokerAdapter):
    broker_id = "five_paisa"

    def __init__(
        self, http: httpx.AsyncClient, base_url: str = "https://Openapi.5paisa.com/VendorsAPI/Service1.svc"
    ):
        self._http = http
        self._base_url = base_url
        self._token: str | None = None
        self._client_code: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        token = creds.extra.get("access_token")
        client_code = creds.extra.get("client_code") or creds.api_key
        if not token or not client_code:
            raise BrokerError("five_paisa_authenticate_requires_access_token_and_client_code")
        self._token = str(token)
        self._client_code = str(client_code)
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._token:
            raise BrokerError("five_paisa_not_authenticated")
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "head": {"key": "5paisa-key"},
            "body": {
                "ClientCode": self._client_code,
                "Exchange": req.exchange[0],  # N/B/M
                "ExchangeType": "C" if req.exchange in ("NSE", "BSE") else "D",
                "ScripCode": int(req.symbol),
                "Price": float(req.price) if req.price is not None else 0,
                "OrderType": req.side[0],  # B/S
                "Qty": int(req.quantity),
                "DisQty": 0,
                "IsIntraday": req.product == "MIS",
                "AHPlaced": "N",
                "RemoteOrderID": req.tag or "DHRUVA",
            },
        }
        response = await self._http.post(
            f"{self._base_url}/V1/PlaceOrderRequest", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "place_order")
        body_resp = data.get("body", {})
        return OrderAck(
            broker_order_id=str(body_resp.get("BrokerOrderID", "")),
            status=str(body_resp.get("Status", "ok")),
        )

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body = {
            "head": {"key": "5paisa-key"},
            "body": {
                "ClientCode": self._client_code,
                "ExchOrderID": broker_order_id,
                "Qty": int(req.quantity) if req.quantity is not None else 0,
                "Price": float(req.price) if req.price is not None else 0,
            },
        }
        response = await self._http.post(
            f"{self._base_url}/V1/ModifyOrderRequest", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        body = {
            "head": {"key": "5paisa-key"},
            "body": {"ClientCode": self._client_code, "ExchOrderID": broker_order_id},
        }
        response = await self._http.post(
            f"{self._base_url}/V1/CancelOrderRequest", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        body = {"head": {"key": "5paisa-key"}, "body": {"ClientCode": self._client_code}}
        response = await self._http.post(
            f"{self._base_url}/V1/NetPosition", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "positions")
        out: list[BrokerPosition] = []
        for item in data.get("body", {}).get("NetPositionDetail", []) or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("ScripName", ""),
                    exchange=item.get("Exch", "N"),
                    quantity=Decimal(str(item.get("NetQty", 0))),
                    average_price=Decimal(str(item.get("AvgRate", 0))),
                    last_price=Decimal(str(item.get("LTP", 0))),
                    pnl=Decimal(str(item.get("BookedPL", 0))),
                    product="MIS",
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        body = {"head": {"key": "5paisa-key"}, "body": {"ClientCode": self._client_code}}
        response = await self._http.post(
            f"{self._base_url}/V2/Holding", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("body", {}).get("Data", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("Symbol", ""),
                    exchange=item.get("Exch", "N"),
                    quantity=Decimal(str(item.get("Quantity", 0))),
                    average_price=Decimal(str(item.get("AvgRate", 0))),
                    last_price=Decimal(str(item.get("CurrentPrice", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        body = {"head": {"key": "5paisa-key"}, "body": {"ClientCode": self._client_code}}
        response = await self._http.post(
            f"{self._base_url}/V3/Margin", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "margin")
        details = (data.get("body", {}).get("EquityMargin", []) or [{}])[0]
        avail = Decimal(str(details.get("AvailableMargin", 0)))
        used = Decimal(str(details.get("MarginUtilized", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        body = {
            "head": {"key": "5paisa-key"},
            "body": {
                "MarketFeedData": [
                    {"Exch": exchange[0], "ExchType": "C", "ScripCode": int(symbol)}
                ],
                "ClientLoginType": 0,
            },
        }
        response = await self._http.post(
            f"{self._base_url}/V1/MarketFeed", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "quote")
        rows = data.get("body", {}).get("Data", []) or [{}]
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(rows[0].get("LastRate", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for sym, exch in symbols:
            out[(sym, exch)] = await self.get_quote(sym, exch)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: 5paisa depth (use MarketDepth endpoint)")

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:  # noqa: ARG002
        raise NotImplementedError("TODO: 5paisa history")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: 5paisa orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: 5paisa tradebook")

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: 5paisa search_symbols")

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, "https://openapi.5paisa.com")

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
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
        if not self._token:
            return {"Accept": "application/json", "Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
