"""Upstox API v2 adapter.

Reference: https://upstox.com/developer/api-documentation/

Best-effort REST mappings against the public v2 documentation. Endpoint
shapes, field names, and product/exchange codes have been verified against
the docs but should be re-tested against the broker sandbox before being
used to place real money. ``search_symbols`` is intentionally unsupported
(it raises ``BrokerError``; resolve symbols from the synced instrument master).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

import httpx

from app.brokers._rest_helpers import (
    epoch_ms_to_ist_date,
    health_probe,
    iter_json_array,
    safe_json,
)
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


INSTRUMENT_URLS: tuple[str, ...] = (
    "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
    "https://assets.upstox.com/market-quote/instruments/exchange/BSE.json.gz",
)

_SEGMENT_TO_EXCHANGE = {
    "NSE_EQ": "NSE",
    "BSE_EQ": "BSE",
    "NSE_INDEX": "NSE",
    "BSE_INDEX": "BSE",
    "NSE_FO": "NFO",
    "BSE_FO": "BFO",
    "NCD_FO": "CDS",
    "BCD_FO": "BCD",
    "MCX_FO": "MCX",
}


def _upstox_instrument(item: dict) -> InstrumentRecord | None:
    key = item.get("instrument_key")
    segment = item.get("segment", "")
    trading_symbol = item.get("trading_symbol") or item.get("tradingsymbol") or ""
    exchange = _SEGMENT_TO_EXCHANGE.get(segment)
    if not key or not trading_symbol or exchange is None:
        return None
    strike_raw = item.get("strike_price")
    # Upstox publishes tick_size in paise (5.0 == Rs 0.05).
    try:
        tick = Decimal(str(item.get("tick_size") or 0)) / Decimal(100)
    except ArithmeticError:
        tick = Decimal(0)
    if tick <= 0:
        tick = Decimal("0.05")
    try:
        lot_size = int(item.get("lot_size") or 1)
    except (TypeError, ValueError):
        lot_size = 1
    return InstrumentRecord(
        symbol=trading_symbol,
        exchange=exchange,
        broker_token=str(key),
        instrument_type=str(item.get("instrument_type") or "EQ"),
        trading_symbol=trading_symbol,
        lot_size=max(lot_size, 1),
        tick_size=tick,
        expiry=epoch_ms_to_ist_date(item.get("expiry")),
        strike=Decimal(str(strike_raw)) if strike_raw not in (None, "", 0, 0.0) else None,
        isin=item.get("isin") or None,
        exchange_token=str(item["exchange_token"]) if item.get("exchange_token") else None,
        extra={
            k: item[k]
            for k in ("name", "segment", "underlying_symbol", "underlying_key", "freeze_quantity")
            if item.get(k) not in (None, "")
        },
    )


class UpstoxAdapter(BrokerAdapter):
    broker_id = "upstox"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = "https://api.upstox.com/v2",
        instrument_urls: tuple[str, ...] = INSTRUMENT_URLS,
    ):
        self._http = http
        self._base_url = base_url
        self._instrument_urls = instrument_urls
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
        response = await self._http.get(
            f"{self._base_url}/order/retrieve-all", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "orderbook")
        out: list[BrokerOrder] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerOrder(
                    broker_order_id=str(item.get("order_id", "")),
                    symbol=item.get("trading_symbol", "") or item.get("tradingsymbol", ""),
                    status=str(item.get("status", "")),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    price=Decimal(str(item.get("price", 0))) if item.get("price") else None,
                )
            )
        return out

    async def get_tradebook(self) -> list[BrokerTrade]:
        response = await self._http.get(
            f"{self._base_url}/order/trades/get-trades-for-day", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "tradebook")
        out: list[BrokerTrade] = []
        for item in data.get("data", []) or []:
            raw_ts = item.get("order_execution_time") or item.get("exchange_timestamp", "")
            try:
                traded_at = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                traded_at = utcnow()
            out.append(
                BrokerTrade(
                    broker_trade_id=str(item.get("trade_id", "")),
                    broker_order_id=str(item.get("order_id", "")),
                    symbol=item.get("trading_symbol", "") or item.get("tradingsymbol", ""),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    price=Decimal(str(item.get("average_price", 0))),
                    traded_at=traded_at,
                )
            )
        return out

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise BrokerError("upstox_search_symbols_not_supported_use_master_contract")

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, f"{self._base_url}/user/profile", self._headers())

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        for url in self._instrument_urls:
            async for item in iter_json_array(self._http, url, self.broker_id, "instruments"):
                record = _upstox_instrument(item)
                if record is not None:
                    yield record

    # ---- Internals --------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
