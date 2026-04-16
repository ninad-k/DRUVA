"""Outbound WebSocket endpoint for browser/SDK clients.

Protocol (JSON over WebSocket):
- client → server: ``{"action":"subscribe","channel":"NSE:RELIANCE"}``
- client → server: ``{"action":"unsubscribe","channel":"NSE:RELIANCE"}``
- server → client: ``{"channel":"NSE:RELIANCE","event":"tick","data":{...}}``

Each connection runs one consumer task per active subscription. Closing the
socket cancels them all.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.data.streaming.hub import StreamHub
from app.data.streaming.types import Tick
from app.infrastructure.logging import get_logger
from app.infrastructure.metrics import active_websocket_connections

logger = get_logger(__name__)


def build_router(hub: StreamHub) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/market")
    async def market_stream(ws: WebSocket) -> None:
        await ws.accept()
        active_websocket_connections.inc()
        tasks: dict[str, asyncio.Task] = {}
        try:
            while True:
                raw = await ws.receive_text()
                msg = _safe_parse(raw)
                if not msg:
                    continue
                action = msg.get("action")
                channel = msg.get("channel")
                if not isinstance(channel, str):
                    continue
                if action == "subscribe" and channel not in tasks:
                    tasks[channel] = asyncio.create_task(_pump(ws, hub, channel))
                elif action == "unsubscribe" and channel in tasks:
                    tasks[channel].cancel()
                    del tasks[channel]
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks.values():
                t.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            active_websocket_connections.dec()

    return router


async def _pump(ws: WebSocket, hub: StreamHub, channel: str) -> None:
    try:
        async for tick in hub.subscribe(channel):
            await ws.send_text(
                json.dumps({"channel": channel, "event": "tick", "data": _tick_dict(tick)})
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws.market.pump_failed", channel=channel, error=str(exc))


def _safe_parse(raw: str) -> Mapping | None:
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _tick_dict(tick: Tick) -> dict:
    return {
        "symbol": tick.symbol,
        "exchange": tick.exchange,
        "last_price": str(tick.last_price),
        "last_quantity": str(tick.last_quantity),
        "ts": tick.ts.isoformat(),
        "bid": str(tick.bid) if tick.bid is not None else None,
        "ask": str(tick.ask) if tick.ask is not None else None,
        "volume": str(tick.volume) if tick.volume is not None else None,
    }
