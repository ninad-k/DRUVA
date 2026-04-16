"""Fyers API v3 adapter.

Reference: https://myapi.fyers.in/docsv3

Fyers tokens follow ``app_id:access_token`` format. Verify against Fyers
sandbox before live use.
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

# Fyers numeric codes
_PRODUCT = {"CNC": "CNC", "MIS": "INTRADAY", "NRML": "MARGIN"}
_ORDER_TYPE = {"LIMIT": 1, "MARKET": 2, "SL": 3, "SL_M": 4}
_SIDE = {"BUY": 1, "SELL": -1}


class FyersAdapter(BrokerAdapter):
    broker_id = "fyers"

    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://api-t1.fyers.in/api/v3"):
        self._http = http
        self._base_url = base_url
        self._token: str | None = None  # `app_id:access_token`

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        access = creds.extra.get("access_token")
        app_id = creds.extra.get("app_id") or creds.api_key
        if not access or not app_id:
            raise BrokerError("fyers_authenticate_requires_app_id_and_access_token")
        self._token = f"{app_id}:{access}"
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._token:
            raise BrokerError("fyers_not_authenticated")
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "symbol": req.symbol,  # caller passes Fyers symbol e.g. NSE:RELIANCE-EQ
            "qty": int(req.quantity),
            "type": _ORDER_TYPE.get(req.order_type, 2),
            "side": _SIDE.get(req.side, 1),
            "productType": _PRODUCT.get(req.product, "INTRADAY"),
            "limitPrice": float(req.price) if req.price is not None else 0,
            "stopPrice": float(req.trigger_price) if req.trigger_price is not None else 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss": 0,
            "takeProfit": 0,
        }
        response = await self._http.post(
            f"{self._base_url}/orders/sync", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "place_order")
        return OrderAck(broker_order_id=str(data.get("id", "")), status=str(data.get("s", "ok")))

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"id": broker_order_id}
        if req.quantity is not None:
            body["qty"] = int(req.quantity)
        if req.price is not None:
            body["limitPrice"] = float(req.price)
        if req.trigger_price is not None:
            body["stopPrice"] = float(req.trigger_price)
        if req.order_type is not None:
            body["type"] = _ORDER_TYPE.get(req.order_type, 2)
        response = await self._http.put(
            f"{self._base_url}/orders/sync", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        response = await self._http.delete(
            f"{self._base_url}/orders/sync",
            params={"id": broker_order_id},
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(f"{self._base_url}/positions", headers=self._headers())
        data = await safe_json(response, self.broker_id, "positions")
        out: list[BrokerPosition] = []
        for item in data.get("netPositions", []) or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("symbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("netQty", 0))),
                    average_price=Decimal(str(item.get("avgPrice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                    pnl=Decimal(str(item.get("pl", 0))),
                    product=item.get("productType", "INTRADAY"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(f"{self._base_url}/holdings", headers=self._headers())
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("holdings", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("symbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("costPrice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(f"{self._base_url}/funds", headers=self._headers())
        data = await safe_json(response, self.broker_id, "margin")
        funds = data.get("fund_limit", []) or []
        # Fyers returns a list keyed by title; pick "Available Balance" + "Utilized Amount".
        avail = used = Decimal("0")
        for f in funds:
            title = f.get("title", "")
            value = Decimal(str(f.get("equityAmount", 0)))
            if title == "Available Balance":
                avail = value
            elif title == "Utilized Amount":
                used = value
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        response = await self._http.get(
            f"{self._base_url}/data/quotes",
            params={"symbols": symbol},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "quote")
        d = (data.get("d") or [{}])[0].get("v", {}) if data.get("d") else {}
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(d.get("lp", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        joined = ",".join(s for s, _ in symbols)
        response = await self._http.get(
            f"{self._base_url}/data/quotes",
            params={"symbols": joined},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "quotes")
        out: dict[tuple[str, str], Quote] = {}
        rows = data.get("d", []) or []
        for entry, (sym, exch) in zip(rows, symbols, strict=False):
            v = entry.get("v", {})
            out[(sym, exch)] = Quote(
                symbol=sym,
                exchange=exch,
                last_price=Decimal(str(v.get("lp", 0))),
                timestamp=utcnow(),
            )
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        response = await self._http.get(
            f"{self._base_url}/data/depth",
            params={"symbol": symbol, "ohlcv_flag": 1},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "depth")
        d = data.get("d", {}).get(symbol, {})

        def _levels(side: list[dict] | None) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("price", 0))),
                    quantity=Decimal(str(lvl.get("volume", 0))),
                    orders=int(lvl.get("ord", 0)),
                )
                for lvl in (side or [])[:5]
            ]

        return Depth(bids=_levels(d.get("bids")), asks=_levels(d.get("ask")))

    async def get_history(
        self,
        symbol: str,
        exchange: str,  # noqa: ARG002
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        f_resolution = {
            "1m": "1",
            "5m": "5",
            "15m": "15",
            "1h": "60",
            "1d": "D",
        }.get(interval, "D")
        response = await self._http.get(
            f"{self._base_url}/data/history",
            params={
                "symbol": symbol,
                "resolution": f_resolution,
                "date_format": 0,
                "range_from": int(start.timestamp()),
                "range_to": int(end.timestamp()),
                "cont_flag": 1,
            },
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "history")
        out: list[Candle] = []
        for row in data.get("candles", []) or []:
            ts, o, h, l, c, v = row
            out.append(
                Candle(
                    symbol=symbol,
                    timeframe=interval,
                    ts=datetime.fromtimestamp(int(ts)),
                    open=Decimal(str(o)),
                    high=Decimal(str(h)),
                    low=Decimal(str(l)),
                    close=Decimal(str(c)),
                    volume=Decimal(str(v)),
                )
            )
        return out

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: fyers orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: fyers tradebook")

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: fyers search_symbols")

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, f"{self._base_url}/profile", self._headers())

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # Fyers publishes per-segment CSVs at https://public.fyers.in/sym_details/.
        # Stub yields nothing — wire URLs at deploy time.
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
            return {"Accept": "application/json"}
        return {"Authorization": self._token, "Accept": "application/json"}
