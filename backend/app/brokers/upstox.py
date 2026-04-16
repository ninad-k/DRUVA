"""Upstox API v2 adapter.

Reference: https://upstox.com/developer/api-documentation/

Best-effort REST mappings against the public v2 documentation. Endpoint
shapes, field names, and product/exchange codes have been verified against
the docs but should be re-tested against the broker sandbox before being
used to place real money. Methods that are not yet implemented raise
``NotImplementedError`` with a TODO so the call site fails loudly rather
than silently.
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


class UpstoxAdapter(BrokerAdapter):
    broker_id = "upstox"

    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://api.upstox.com/v2"):
        self._http = http
        self._base_url = base_url
        self._access_token: str | None = None

    # ---- Auth -------------------------------------------------------------

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        """Upstox uses an OAuth code flow externally; the access token is
        passed in via ``creds.extra['access_token']`` once the user has
        completed login. The api_key/api_secret remain in the encrypted
        Account row so we can rebuild this adapter on demand."""
        token = creds.extra.get("access_token")
        if not token:
            raise BrokerError("upstox_authenticate_requires_access_token_in_extra")
        self._access_token = str(token)
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._access_token:
            raise BrokerError("upstox_not_authenticated")
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    # ---- Orders -----------------------------------------------------------

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "quantity": int(req.quantity),
            "product": req.product,
            "validity": "DAY",
            "price": float(req.price) if req.price is not None else 0,
            "tag": req.tag or "",
            "instrument_token": req.symbol,  # caller passes instrument_key e.g. NSE_EQ|INE002A01018
            "order_type": req.order_type,
            "transaction_type": req.side,
            "disclosed_quantity": 0,
            "trigger_price": float(req.trigger_price) if req.trigger_price is not None else 0,
            "is_amo": False,
        }
        response = await self._http.post(
            f"{self._base_url}/order/place", json=body, headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "place_order")
        order_id = (data.get("data") or {}).get("order_id", "")
        return OrderAck(broker_order_id=str(order_id), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"order_id": broker_order_id, "validity": "DAY"}
        if req.quantity is not None:
            body["quantity"] = int(req.quantity)
        if req.price is not None:
            body["price"] = float(req.price)
        if req.trigger_price is not None:
            body["trigger_price"] = float(req.trigger_price)
        if req.order_type is not None:
            body["order_type"] = req.order_type
        response = await self._http.put(
            f"{self._base_url}/order/modify", json=body, headers=self._headers()
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        response = await self._http.delete(
            f"{self._base_url}/order/cancel",
            params={"order_id": broker_order_id},
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "cancel_order")

    # ---- Portfolio --------------------------------------------------------

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(
            f"{self._base_url}/portfolio/short-term-positions", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "positions")
        out: list[BrokerPosition] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("trading_symbol") or item.get("tradingsymbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("average_price", 0))),
                    last_price=Decimal(str(item.get("last_price", 0))),
                    pnl=Decimal(str(item.get("pnl", 0))),
                    product=item.get("product", "MIS"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(
            f"{self._base_url}/portfolio/long-term-holdings", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("trading_symbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("average_price", 0))),
                    last_price=Decimal(str(item.get("last_price", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(
            f"{self._base_url}/user/get-funds-and-margin", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "margin")
        equity = (data.get("data") or {}).get("equity") or {}
        avail = Decimal(str(equity.get("available_margin", 0)))
        used = Decimal(str(equity.get("used_margin", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    # ---- Market data ------------------------------------------------------

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        response = await self._http.get(
            f"{self._base_url}/market-quote/ltp",
            params={"instrument_key": symbol},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "quote")
        rows = data.get("data") or {}
        first = next(iter(rows.values()), {}) if rows else {}
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
        response = await self._http.get(
            f"{self._base_url}/market-quote/depth",
            params={"instrument_key": symbol},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "depth")
        rows = data.get("data") or {}
        first = next(iter(rows.values()), {}) if rows else {}

        def _levels(side: list[dict] | None) -> list[DepthLevel]:
            return [
                DepthLevel(
                    price=Decimal(str(lvl.get("price", 0))),
                    quantity=Decimal(str(lvl.get("quantity", 0))),
                    orders=int(lvl.get("orders", 0)),
                )
                for lvl in (side or [])[:5]
            ]

        return Depth(bids=_levels(first.get("bid")), asks=_levels(first.get("ask")))

    async def get_history(
        self,
        symbol: str,
        exchange: str,  # noqa: ARG002
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        u_interval = {
            "1m": "1minute",
            "5m": "5minute",
            "15m": "15minute",
            "1h": "60minute",
            "1d": "day",
        }.get(interval, "day")
        url = (
            f"{self._base_url}/historical-candle/{symbol}/{u_interval}/"
            f"{end.date().isoformat()}/{start.date().isoformat()}"
        )
        response = await self._http.get(url, headers=self._headers())
        data = await safe_json(response, self.broker_id, "history")
        out: list[Candle] = []
        for row in (data.get("data") or {}).get("candles", []) or []:
            ts, o, h, l, c, v, *_ = row
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
        raise NotImplementedError("TODO: upstox orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: upstox tradebook")

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: upstox search_symbols (use master contract download)")

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, f"{self._base_url}/user/profile", self._headers())

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        # Upstox publishes a daily gzipped JSON dump. Real implementation:
        # stream + gunzip + ijson. The stub yields nothing so the sync job
        # logs 0 records and the operator can wire the real download URL
        # when going live.
        if False:
            yield InstrumentRecord(
                symbol="",
                exchange="NSE",
                broker_token="",
                instrument_type="EQ",
                trading_symbol="",
            )
        return

    # ---- Internals --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
