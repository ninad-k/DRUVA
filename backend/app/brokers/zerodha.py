from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal

import httpx

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
from app.utils.time import utcnow


class ZerodhaAdapter(BrokerAdapter):
    broker_id = "zerodha"

    def __init__(self, http: httpx.AsyncClient, base_url: str = "https://api.kite.trade"):
        self._http = http
        self._base_url = base_url
        self._access_token: str | None = None

    async def authenticate(self, creds: BrokerCredentials) -> AuthSession:
        self._access_token = creds.extra.get("access_token")
        return AuthSession(access_token=self._access_token or "", refresh_token=None, expires_at=None)

    async def refresh_token(self) -> AuthSession:
        if self._access_token is None:
            raise BrokerError("zerodha_not_authenticated")
        return AuthSession(access_token=self._access_token, refresh_token=None, expires_at=None)

    async def place_order(self, req: OrderRequest) -> OrderAck:
        payload = {
            "tradingsymbol": req.symbol,
            "exchange": req.exchange,
            "transaction_type": req.side,
            "quantity": int(req.quantity),
            "order_type": req.order_type,
            "product": req.product,
            "price": float(req.price) if req.price is not None else None,
            "trigger_price": float(req.trigger_price) if req.trigger_price is not None else None,
        }
        headers = self._headers()
        response = await self._http.post(f"{self._base_url}/orders/regular", data=payload, headers=headers)
        if response.status_code >= 400:
            raise BrokerError(f"zerodha_place_order_failed:{response.text}")
        data = response.json().get("data", {})
        return OrderAck(broker_order_id=str(data.get("order_id", "")), status="accepted")

    async def modify_order(self, broker_order_id: str, req: OrderModifyRequest) -> OrderAck:
        raise NotImplementedError("TODO: zerodha modify_order")

    async def cancel_order(self, broker_order_id: str) -> None:
        response = await self._http.delete(
            f"{self._base_url}/orders/regular/{broker_order_id}",
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise BrokerError(f"zerodha_cancel_order_failed:{response.text}")

    async def get_positions(self) -> list[BrokerPosition]:
        response = await self._http.get(f"{self._base_url}/portfolio/positions", headers=self._headers())
        if response.status_code >= 400:
            raise BrokerError("zerodha_positions_failed")
        net = response.json().get("data", {}).get("net", [])
        out: list[BrokerPosition] = []
        for item in net:
            out.append(
                BrokerPosition(
                    symbol=item.get("tradingsymbol", ""),
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
        raise NotImplementedError("TODO: zerodha holdings")

    async def get_margin(self) -> MarginDetails:
        return MarginDetails(available_cash=Decimal("1000000"), used_margin=Decimal("0"), total=Decimal("1000000"))

    async def health(self) -> BrokerHealth:
        started = datetime.now().timestamp()
        try:
            await self._http.get(f"{self._base_url}/instruments", headers=self._headers())
            latency_ms = (datetime.now().timestamp() - started) * 1000
            return BrokerHealth(is_healthy=True, latency_ms=latency_ms)
        except Exception as exc:  # noqa: BLE001
            latency_ms = (datetime.now().timestamp() - started) * 1000
            return BrokerHealth(is_healthy=False, latency_ms=latency_ms, message=str(exc))

    async def search_symbols(self, query: str, exchange: str | None = None) -> list[InstrumentMatch]:
        raise NotImplementedError("TODO: zerodha search_symbols")

    async def get_quote(self, symbol: str, exchange: str) -> Quote:
        response = await self._http.get(
            f"{self._base_url}/quote",
            params={"i": f"{exchange}:{symbol}"},
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise BrokerError("zerodha_quote_failed")
        data = response.json().get("data", {})
        value = data.get(f"{exchange}:{symbol}", {})
        return Quote(
            symbol=symbol,
            exchange=exchange,
            last_price=Decimal(str(value.get("last_price", 0))),
            timestamp=utcnow(),
        )

    async def get_quotes(self, symbols: list[tuple[str, str]]) -> dict[tuple[str, str], Quote]:
        out: dict[tuple[str, str], Quote] = {}
        for symbol, exchange in symbols:
            out[(symbol, exchange)] = await self.get_quote(symbol, exchange)
        return out

    async def get_depth(self, symbol: str, exchange: str) -> Depth:
        raise NotImplementedError("TODO: zerodha depth")

    async def get_history(self, symbol: str, exchange: str, interval: str, start: datetime, end: datetime):  # type: ignore[override]
        raise NotImplementedError("TODO: zerodha history")

    async def get_orderbook(self) -> list[BrokerOrder]:
        raise NotImplementedError("TODO: zerodha orderbook")

    async def get_tradebook(self) -> list[BrokerTrade]:
        raise NotImplementedError("TODO: zerodha tradebook")

    async def download_master_contract(self) -> AsyncIterator[InstrumentRecord]:
        response = await self._http.get(f"{self._base_url}/instruments", headers=self._headers())
        if response.status_code >= 400:
            raise BrokerError("zerodha_instruments_failed")
        # Kite returns CSV; parsing is intentionally minimal for phase1.
        lines = response.text.splitlines()
        for line in lines[1:]:
            cols = line.split(",")
            if len(cols) < 12:
                continue
            yield InstrumentRecord(
                symbol=cols[2],
                exchange=cols[11],
                broker_token=cols[0],
                instrument_type="EQ",
                trading_symbol=cols[2],
                lot_size=int(cols[8] or 1),
                tick_size=Decimal(cols[7] or "0.05"),
                exchange_token=cols[1] or None,
            )

    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            return {}
        return {"Authorization": f"token {self._access_token}"}
