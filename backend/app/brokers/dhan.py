"""Dhan API v2 adapter.

Reference: https://dhanhq.co/docs/v2/

Dhan uses an ``access-token`` header (not Bearer). Instrument identifiers are
``securityId`` (numeric string). Best-effort REST mappings — verify against
the Dhan sandbox before live use.
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


class DhanAdapter(BrokerAdapter):
    broker_id = "dhan"

    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://api.dhan.co/v2"):
        self._http = http
        self._base_url = base_url
        self._access_token: str | None = None
        self._client_id: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        token = creds.extra.get("access_token") or creds.api_secret
        client_id = creds.extra.get("client_id") or creds.api_key
        if not token or not client_id:
            raise BrokerError("dhan_authenticate_requires_access_token_and_client_id")
        self._access_token = str(token)
        self._client_id = str(client_id)
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._access_token:
            raise BrokerError("dhan_not_authenticated")
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "dhanClientId": self._client_id,
            "transactionType": req.side,
            "exchangeSegment": _dhan_segment(req.exchange),
            "productType": _dhan_product(req.product),
            "orderType": req.order_type,
            "validity": "DAY",
            "securityId": req.symbol,
            "quantity": int(req.quantity),
            "disclosedQuantity": 0,
            "price": float(req.price) if req.price is not None else 0,
            "triggerPrice": float(req.trigger_price) if req.trigger_price is not None else 0,
        }
        response = await self._http.post(
            f"{self._base_url}/orders", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "place_order")
        return OrderAck(broker_order_id=str(data.get("orderId", "")), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"dhanClientId": self._client_id, "orderId": broker_order_id}
        if req.quantity is not None:
            body["quantity"] = int(req.quantity)
        if req.price is not None:
            body["price"] = float(req.price)
        if req.trigger_price is not None:
            body["triggerPrice"] = float(req.trigger_price)
        if req.order_type is not None:
            body["orderType"] = req.order_type
        response = await self._http.put(
            f"{self._base_url}/orders/{broker_order_id}", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        response = await self._http.delete(
            f"{self._base_url}/orders/{broker_order_id}", headers=self._headers()
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(f"{self._base_url}/positions", headers=self._headers())
        items = await safe_json(response, self.broker_id, "positions")
        # Dhan returns a top-level list.
        rows = items if isinstance(items, list) else items.get("data", [])
        out: list[BrokerPosition] = []
        for item in rows or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchangeSegment", "NSE"),
                    quantity=Decimal(str(item.get("netQty", 0))),
                    average_price=Decimal(str(item.get("avgCostPrice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                    pnl=Decimal(str(item.get("realizedProfit", 0))),
                    product=item.get("productType", "MIS"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(f"{self._base_url}/holdings", headers=self._headers())
        items = await safe_json(response, self.broker_id, "holdings")
        rows = items if isinstance(items, list) else items.get("data", [])
        out: list[BrokerHolding] = []
        for item in rows or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("tradingSymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("totalQty", 0))),
                    average_price=Decimal(str(item.get("avgCostPrice", 0))),
                    last_price=Decimal(str(item.get("lastTradedPrice", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(f"{self._base_url}/fundlimit", headers=self._headers())
        data = await safe_json(response, self.broker_id, "margin")
        avail = Decimal(str(data.get("availabelBalance", data.get("availableBalance", 0))))
        used = Decimal(str(data.get("utilizedAmount", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        body = {_dhan_segment(exchange): [int(symbol)]}
        response = await self._http.post(
            f"{self._base_url}/marketfeed/ltp", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "quote")
        seg = data.get("data", {}).get(_dhan_segment(exchange), {})
        first = next(iter(seg.values()), {}) if seg else {}
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(first.get("last_price", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for symbol, exchange in symbols:
            out[(symbol, exchange)] = await self.get_quote(symbol, exchange)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        body = {_dhan_segment(exchange): [int(symbol)]}
        response = await self._http.post(
            f"{self._base_url}/marketfeed/quote", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "depth")
        seg = data.get("data", {}).get(_dhan_segment(exchange), {})
        first = next(iter(seg.values()), {}) if seg else {}
        depth = first.get("depth", {})

        def _levels(side: list[dict] | None) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("price", 0))),
                    quantity=Decimal(str(lvl.get("quantity", 0))),
                    orders=int(lvl.get("orders", 0)),
                )
                for lvl in (side or [])[:5]
            ]

        return Depth(bids=_levels(depth.get("buy")), asks=_levels(depth.get("sell")))

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        # Dhan uses /charts/historical for daily and /charts/intraday for intraday.
        is_intraday = interval != "1d"
        endpoint = "intraday" if is_intraday else "historical"
        body = {
            "securityId": symbol,
            "exchangeSegment": _dhan_segment(exchange),
            "instrument": "EQUITY",
            "interval": {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}.get(interval, "1"),
            "fromDate": start.date().isoformat(),
            "toDate": end.date().isoformat(),
        }
        response = await self._http.post(
            f"{self._base_url}/charts/{endpoint}", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "history")
        opens = data.get("open", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        closes = data.get("close", [])
        volumes = data.get("volume", [])
        timestamps = data.get("timestamp", [])
        out: list[Candle] = []
        for i, ts in enumerate(timestamps):
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=datetime.fromtimestamp(int(ts)),
                    open=Decimal(str(opens[i])),
                    high=Decimal(str(highs[i])),
                    low=Decimal(str(lows[i])),
                    close=Decimal(str(closes[i])),
                    volume=Decimal(str(volumes[i])),
                )
            )
        return out

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: dhan orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: dhan tradebook")

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: dhan search_symbols")

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, f"{self._base_url}/profile", self._headers())

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # Dhan publishes a daily CSV. Real implementation needs streaming +
        # CSV parsing; stub yields nothing so the operator wires the URL.
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
        if not self._access_token:
            return {"Accept": "application/json"}
        return {
            "access-token": self._access_token,
            "Accept": "application/json",
        }


def _dhan_segment(exchange: str) -> str:
    return {
        "NSE": "NSE_EQ",
        "BSE": "BSE_EQ",
        "NFO": "NSE_FNO",
        "BFO": "BSE_FNO",
        "MCX": "MCX_COMM",
        "CDS": "NSE_CURRENCY",
    }.get(exchange, "NSE_EQ")


def _dhan_product(product: str) -> str:
    return {"MIS": "INTRADAY", "CNC": "CNC", "NRML": "MARGIN"}.get(product, "INTRADAY")
