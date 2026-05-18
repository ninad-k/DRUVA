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

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        body = {
            "head": {"key": "5paisa-key"},
            "body": {
                "Count": 1,
                "Data": [
                    {
                        "Exchange": exchange[0],
                        "ExchangeType": "C" if exchange in ("NSE", "BSE") else "D",
                        "ScripCode": int(symbol),
                    }
                ],
            },
        }
        response = await self._http.post(
            f"{self._base_url}/V1/MarketDepth", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "depth")
        detail = (data.get("body", {}).get("Data", []) or [{}])[0]

        def _levels(side: list[dict] | None) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("Price", 0))),
                    quantity=Decimal(str(lvl.get("Quantity", 0))),
                )
                for lvl in (side or [])[:5]
            ]

        return Depth(
            bids=_levels(detail.get("Bids", detail.get("BidData", []))),
            asks=_levels(detail.get("Offers", detail.get("AskData", []))),
        )

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        # 5paisa historical candle endpoint uses TimeSeries API.
        fp_interval = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}.get(interval, "1D")
        body = {
            "head": {"key": "5paisa-key"},
            "body": {
                "Exchange": exchange[0],
                "ExchangeType": "C" if exchange in ("NSE", "BSE") else "D",
                "ScripCode": int(symbol),
                "StartDate": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "EndDate": end.strftime("%Y-%m-%dT%H:%M:%S"),
                "Interval": fp_interval,
            },
        }
        response = await self._http.post(
            f"{self._base_url}/V1/HistoricalData", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "history")
        out: list[Candle] = []
        for item in data.get("body", {}).get("Data", []) or []:
            raw_ts = item.get("DateTime", item.get("dt", ""))
            try:
                ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                ts = utcnow()
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=ts,
                    open=Decimal(str(item.get("Open", 0))),
                    high=Decimal(str(item.get("High", 0))),
                    low=Decimal(str(item.get("Low", 0))),
                    close=Decimal(str(item.get("Close", 0))),
                    volume=Decimal(str(item.get("Volume", 0))),
                )
            )
        return out

    async def get_orderbook(self) -> list[BrokerOrder]:
        body = {"head": {"key": "5paisa-key"}, "body": {"ClientCode": self._client_code}}
        response = await self._http.post(
            f"{self._base_url}/V1/OrderBook", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "orderbook")
        out: list[BrokerOrder] = []
        for item in data.get("body", {}).get("OrderBookDetail", []) or []:
            out.append(
                BrokerOrder(
                    broker_order_id=str(item.get("ExchOrderID", item.get("BrokerOrderID", ""))),
                    symbol=item.get("ScripName", ""),
                    status=str(item.get("OrderStatus", "")),
                    quantity=Decimal(str(item.get("Qty", 0))),
                    price=Decimal(str(item.get("Rate", 0))) if item.get("Rate") else None,
                )
            )
        return out

    async def get_tradebook(self) -> list[BrokerTrade]:
        body = {"head": {"key": "5paisa-key"}, "body": {"ClientCode": self._client_code}}
        response = await self._http.post(
            f"{self._base_url}/V1/TradeBook", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "tradebook")
        out: list[BrokerTrade] = []
        for item in data.get("body", {}).get("TradeBookDetail", []) or []:
            raw_ts = item.get("ExchDt") or item.get("ExchTime", "")
            try:
                traded_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                traded_at = utcnow()
            out.append(
                BrokerTrade(
                    broker_trade_id=str(item.get("ExchOrderID", "")),
                    broker_order_id=str(item.get("BrokerOrderID", "")),
                    symbol=item.get("ScripName", ""),
                    quantity=Decimal(str(item.get("Qty", 0))),
                    price=Decimal(str(item.get("Rate", 0))),
                    traded_at=traded_at,
                )
            )
        return out

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise BrokerError("five_paisa_search_symbols_not_supported_use_master_contract")

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
