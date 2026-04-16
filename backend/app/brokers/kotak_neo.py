"""Kotak Neo TradeAPI adapter.

Reference: https://documenter.getpostman.com/view/21534097/Uz5GnvaL

Kotak Neo uses HS256 + view tokens; the typical flow is to exchange a
client_id/secret + OTP for a session. We treat the final ``session_token``
as the credential since DHRUVA accounts always store derived tokens, not
passwords.
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


class KotakNeoAdapter(BrokerAdapter):
    broker_id = "kotak_neo"

    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://gw-napi.kotaksecurities.com"):
        self._http = http
        self._base_url = base_url
        self._token: str | None = None
        self._sid: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        token = creds.extra.get("access_token")
        sid = creds.extra.get("sid")
        if not token or not sid:
            raise BrokerError("kotak_neo_authenticate_requires_access_token_and_sid")
        self._token = str(token)
        self._sid = str(sid)
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._token:
            raise BrokerError("kotak_neo_not_authenticated")
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "am": "NO",
            "dq": "0",
            "es": req.exchange,
            "mp": "0",
            "pc": req.product,
            "pf": "N",
            "pr": str(float(req.price)) if req.price is not None else "0",
            "pt": req.order_type,
            "qt": str(int(req.quantity)),
            "rt": "DAY",
            "tp": str(float(req.trigger_price)) if req.trigger_price is not None else "0",
            "ts": req.symbol,
            "tt": req.side[0],  # B or S
        }
        response = await self._http.post(
            f"{self._base_url}/Orders/2.0/quick/order/rule/ms/place",
            data={"jData": _to_json(body)},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "place_order")
        return OrderAck(broker_order_id=str(data.get("nOrdNo", "")), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"on": broker_order_id}
        if req.quantity is not None:
            body["qt"] = str(int(req.quantity))
        if req.price is not None:
            body["pr"] = str(float(req.price))
        if req.trigger_price is not None:
            body["tp"] = str(float(req.trigger_price))
        if req.order_type is not None:
            body["pt"] = req.order_type
        response = await self._http.post(
            f"{self._base_url}/Orders/2.0/quick/order/vr/modify",
            data={"jData": _to_json(body)},
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        body = {"on": broker_order_id}
        response = await self._http.post(
            f"{self._base_url}/Orders/2.0/quick/order/cancel",
            data={"jData": _to_json(body)},
            headers=self._headers(),
        )
        await safe_json(response, self.broker_id, "cancel_order")

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(
            f"{self._base_url}/Orders/2.0/quick/user/positions", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "positions")
        out: list[BrokerPosition] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerPosition(
                    symbol=item.get("trdSym", ""),
                    exchange=item.get("exSeg", "NSE"),
                    quantity=Decimal(str(item.get("flBuyQty", 0))) - Decimal(str(item.get("flSellQty", 0))),
                    average_price=Decimal(str(item.get("avgnetprice", 0))),
                    last_price=Decimal(str(item.get("ltp", 0))),
                    pnl=Decimal(str(item.get("rpnl", 0))),
                    product=item.get("prod", "MIS"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        response = await self._http.get(
            f"{self._base_url}/Portfolio/1.0/portfolio/v1/holdings", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "holdings")
        out: list[BrokerHolding] = []
        for item in data.get("data", []) or []:
            out.append(
                BrokerHolding(
                    symbol=item.get("symbol", ""),
                    exchange=item.get("exchange", "NSE"),
                    quantity=Decimal(str(item.get("quantity", 0))),
                    average_price=Decimal(str(item.get("averagePrice", 0))),
                    last_price=Decimal(str(item.get("closingPrice", 0))),
                )
            )
        return out

    async def get_margin(self) -> MarginDetails:
        response = await self._http.get(
            f"{self._base_url}/Orders/2.0/quick/user/limits", headers=self._headers()
        )
        data = await safe_json(response, self.broker_id, "margin")
        avail = Decimal(str(data.get("Net", 0)))
        used = Decimal(str(data.get("MarginUsed", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        body = {"in": [{"is": symbol, "es": exchange}]}
        response = await self._http.post(
            f"{self._base_url}/quotes/v1/touch",
            data={"jData": _to_json(body)},
            headers=self._headers(),
        )
        data = await safe_json(response, self.broker_id, "quote")
        rows = data.get("data", []) or [{}]
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(rows[0].get("ltp", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for s, e in symbols:
            out[(s, e)] = await self.get_quote(s, e)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: kotak_neo depth")

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:  # noqa: ARG002
        raise NotImplementedError("TODO: kotak_neo history")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: kotak_neo orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: kotak_neo tradebook")

    async def search_symbols(
        self,
        query: str,  # noqa: ARG002
        exchange: str | None = None,  # noqa: ARG002
    ) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: kotak_neo search_symbols")

    async def health(self) -> BrokerHealth:
        return await health_probe(
            self._http,
            f"{self._base_url}/Orders/2.0/quick/user/profile",
            self._headers(),
        )

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
        if not self._token or not self._sid:
            return {"Accept": "application/json"}
        return {
            "Authorization": f"Bearer {self._token}",
            "Sid": self._sid,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }


def _to_json(body: dict) -> str:
    import json

    return json.dumps(body)
