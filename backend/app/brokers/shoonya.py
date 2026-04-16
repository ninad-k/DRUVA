"""Shoonya / Finvasia (Flattrade) NorenAPI adapter.

Reference: https://prism.shoonya.com/api

Shoonya/Finvasia/Flattrade all share the NorenAPI base; this adapter targets
the standard endpoint set. Verify against the broker's UAT environment
before live use.
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


class ShoonyaAdapter(BrokerAdapter):
    broker_id = "shoonya"

    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str = "https://api.shoonya.com/NorenWClientTP",
    ):
        self._http = http
        self._base_url = base_url
        self._uid: str | None = None
        self._token: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        uid = creds.extra.get("user_id") or creds.api_key
        token = creds.extra.get("session_token") or creds.extra.get("access_token")
        if not uid or not token:
            raise BrokerError("shoonya_authenticate_requires_user_id_and_session_token")
        self._uid = str(uid)
        self._token = str(token)
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if not self._token:
            raise BrokerError("shoonya_not_authenticated")
        return AuthSession(access_token=self._token, refresh_token=None, expires_at=None)

    async def _post(self, path: str, payload: dict, op: str) -> dict:
        # NorenAPI uses x-www-form-urlencoded with two fields: jData (JSON) + jKey (token).
        import json

        data = {"jData": json.dumps(payload), "jKey": self._token or ""}
        response = await self._http.post(f"{self._base_url}/{path}", data=data)
        return await safe_json(response, self.broker_id, op)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        body = {
            "uid": self._uid,
            "actid": self._uid,
            "exch": req.exchange,
            "tsym": req.symbol,
            "qty": str(int(req.quantity)),
            "prc": str(float(req.price)) if req.price is not None else "0",
            "trgprc": str(float(req.trigger_price)) if req.trigger_price is not None else "0",
            "prd": {"MIS": "I", "CNC": "C", "NRML": "M"}.get(req.product, "I"),
            "trantype": req.side[0],  # B / S
            "prctyp": _shoonya_prctyp(req.order_type),
            "ret": "DAY",
            "remarks": req.tag or "DHRUVA",
        }
        data = await self._post("PlaceOrder", body, "place_order")
        return OrderAck(broker_order_id=str(data.get("norenordno", "")), status=str(data.get("stat", "ok")))

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        body: dict = {"uid": self._uid, "norenordno": broker_order_id}
        if req.quantity is not None:
            body["qty"] = str(int(req.quantity))
        if req.price is not None:
            body["prc"] = str(float(req.price))
        if req.trigger_price is not None:
            body["trgprc"] = str(float(req.trigger_price))
        if req.order_type is not None:
            body["prctyp"] = _shoonya_prctyp(req.order_type)
        await self._post("ModifyOrder", body, "modify_order")
        return OrderAck(broker_order_id=broker_order_id, status="modified")

    async def cancel_order(self, broker_order_id: str) -> None:
        await self._post(
            "CancelOrder", {"uid": self._uid, "norenordno": broker_order_id}, "cancel_order"
        )

    async def get_positions(self) -> list[BrokerPosition]:
        data = await self._post("PositionBook", {"uid": self._uid, "actid": self._uid}, "positions")
        rows = data if isinstance(data, list) else []
        out: list[BrokerPosition] = []
        for item in rows:
            out.append(
                BrokerPosition(
                    symbol=item.get("tsym", ""),
                    exchange=item.get("exch", "NSE"),
                    quantity=Decimal(str(item.get("netqty", 0))),
                    average_price=Decimal(str(item.get("netavgprc", 0))),
                    last_price=Decimal(str(item.get("lp", 0))),
                    pnl=Decimal(str(item.get("rpnl", 0))),
                    product=item.get("prd", "I"),
                )
            )
        return out

    async def get_holdings(self) -> list[BrokerHolding]:
        data = await self._post("Holdings", {"uid": self._uid, "actid": self._uid, "prd": "C"}, "holdings")
        rows = data if isinstance(data, list) else []
        out: list[BrokerHolding] = []
        for item in rows:
            holdings = item.get("exch_tsym", []) or []
            for h in holdings:
                out.append(
                    BrokerHolding(
                        symbol=h.get("tsym", ""),
                        exchange=h.get("exch", "NSE"),
                        quantity=Decimal(str(item.get("npoadqty", 0))),
                        average_price=Decimal(str(item.get("upldprc", 0))),
                        last_price=Decimal("0"),
                    )
                )
        return out

    async def get_margin(self) -> MarginDetails:
        data = await self._post("Limits", {"uid": self._uid, "actid": self._uid}, "margin")
        avail = Decimal(str(data.get("cash", 0)))
        used = Decimal(str(data.get("marginused", 0)))
        return MarginDetails(available_cash=avail, used_margin=used, total=avail + used)

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        data = await self._post(
            "GetQuotes", {"uid": self._uid, "exch": exchange, "token": symbol}, "quote"
        )
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(data.get("lp", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for s, e in symbols:
            out[(s, e)] = await self.get_quote(s, e)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:  # noqa: ARG002
        raise NotImplementedError("TODO: shoonya depth (use GetQuotes; depth in same payload)")

    async def get_history(
        self,
        symbol: str,
        exchange: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:  # noqa: ARG002
        raise NotImplementedError("TODO: shoonya history (TPSeries endpoint)")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: shoonya orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: shoonya tradebook")

    async def search_symbols(
        self,
        query: str,
        exchange: str | None = None,
    ) -> list[InstrumentMatch]:
        data = await self._post(
            "SearchScrip",
            {"uid": self._uid, "stext": query, "exch": exchange or "NSE"},
            "search",
        )
        out: list[InstrumentMatch] = []
        for item in data.get("values", []) or []:
            out.append(
                InstrumentMatch(
                    symbol=item.get("tsym", ""),
                    exchange=item.get("exch", "NSE"),
                    broker_token=item.get("token", ""),
                    instrument_type="EQ",
                )
            )
        return out

    async def health(self) -> BrokerHealth:
        return await health_probe(self._http, self._base_url)

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


def _shoonya_prctyp(order_type: str) -> str:
    return {"MARKET": "MKT", "LIMIT": "LMT", "SL": "SL-LMT", "SL_M": "SL-MKT"}.get(order_type, "MKT")
