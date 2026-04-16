"""DHRUVA MCP server.

Exposes a small set of tools that LLM clients can call:

    list_accounts() -> [{id, broker_id, is_paper, ...}]
    list_positions(account_id) -> [...]
    list_orders(account_id) -> [...]
    place_order(account_id, symbol, exchange, side, quantity, order_type, product, price?) -> Order
    list_strategies(account_id) -> [...]
    enable_strategy(strategy_id), disable_strategy(strategy_id)
    get_option_chain(account_id, underlying, expiry, spot) -> chain dict
    get_market_calendar(exchange) -> {open, holidays, sessions}

Auth: the MCP client passes a DHRUVA JWT via the ``DHRUVA_MCP_TOKEN``
environment variable; we validate it on every tool call. Without a valid
token every call returns a permission error — no anonymous access.

Run with: ``python -m app.mcp.server`` (requires ``mcp`` Python SDK).
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.api.dependencies import build_execution_service_for_session
from app.cache.client import CacheClient
from app.config import get_settings
from app.core.auth.tokens import TokenService
from app.core.notifications.telegram import TelegramNotifier
from app.db.models.account import Account
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import SessionLocal
from app.infrastructure.http import get_http_client
from app.infrastructure.logging import configure_logging, get_logger
from app.infrastructure.redis import get_redis

logger = get_logger(__name__)


async def _current_user_id() -> str:
    """Validate the MCP token and return the bearer's user id."""
    token = os.environ.get("DHRUVA_MCP_TOKEN")
    if not token:
        raise PermissionError("DHRUVA_MCP_TOKEN env var not set")
    settings = get_settings()
    return TokenService(settings).decode_access_token(token)


async def _ensure_user(user_id: str) -> User:
    async with SessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise PermissionError("user_not_found")
        return user


# ---------------------------------------------------------------------------
# Tool implementations (plain async functions — wrapped by the MCP server)
# ---------------------------------------------------------------------------


async def list_accounts() -> list[dict[str, Any]]:
    user_id = await _current_user_id()
    async with SessionLocal() as session:
        rows = (
            await session.execute(select(Account).where(Account.user_id == user_id))
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "broker_id": r.broker_id,
                "is_paper": r.is_paper,
                "is_active": r.is_active,
            }
            for r in rows
        ]


async def list_positions(account_id: str) -> list[dict[str, Any]]:
    user_id = await _current_user_id()
    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        if account is None or str(account.user_id) != user_id:
            raise PermissionError("account_not_found")
        rows = (
            await session.execute(select(Position).where(Position.account_id == account.id))
        ).scalars().all()
        return [
            {
                "symbol": r.symbol,
                "exchange": str(r.exchange),
                "quantity": str(r.quantity),
                "avg_cost": str(r.avg_cost),
                "realized_pnl": str(r.realized_pnl),
            }
            for r in rows
        ]


async def list_orders(account_id: str, limit: int = 20) -> list[dict[str, Any]]:
    user_id = await _current_user_id()
    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        if account is None or str(account.user_id) != user_id:
            raise PermissionError("account_not_found")
        rows = (
            await session.execute(
                select(Order)
                .where(Order.account_id == account.id)
                .order_by(Order.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "symbol": r.symbol,
                "side": str(r.side),
                "quantity": str(r.quantity),
                "status": str(r.status),
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


async def place_order(
    account_id: str,
    symbol: str,
    exchange: str,
    side: str,
    quantity: str,
    order_type: str = "MARKET",
    product: str = "MIS",
    price: str | None = None,
) -> dict[str, Any]:
    """Place a live or paper order on behalf of the MCP-authenticated user.

    Routes through ExecutionService — risk checks, audit, and Telegram
    emission all run as if the order came in over REST.
    """
    user_id = await _current_user_id()
    user = await _ensure_user(user_id)
    settings = get_settings()
    http = await _http()
    redis = await _redis()
    cache = CacheClient(redis)
    notifier = TelegramNotifier(bot_token=settings.telegram_bot_token, http=http)

    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        if account is None or str(account.user_id) != str(user.id):
            raise PermissionError("account_not_found")
        execution = build_execution_service_for_session(
            session=session,
            http=http,
            cache=cache,
            redis=redis,
            settings=settings,
            notifier=notifier,
        )
        from app.core.execution.models import PlaceOrderRequest

        order = await execution.place_order(
            user_id=str(user.id),
            req=PlaceOrderRequest(
                account_id=account.id,
                symbol=symbol,
                exchange=exchange,
                side=side.upper(),  # type: ignore[arg-type]
                quantity=Decimal(quantity),
                order_type=order_type.upper(),  # type: ignore[arg-type]
                product=product.upper(),  # type: ignore[arg-type]
                price=Decimal(price) if price else None,
            ),
        )
        return {
            "id": str(order.id),
            "symbol": order.symbol,
            "status": str(order.status),
        }


async def list_strategies(account_id: str) -> list[dict[str, Any]]:
    user_id = await _current_user_id()
    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        if account is None or str(account.user_id) != user_id:
            raise PermissionError("account_not_found")
        rows = (
            await session.execute(
                select(Strategy).where(
                    Strategy.account_id == account.id,
                    Strategy.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "strategy_class": r.strategy_class,
                "is_enabled": r.is_enabled,
                "is_ml": r.is_ml,
                "mode": str(r.mode),
            }
            for r in rows
        ]


async def toggle_strategy(strategy_id: str, enabled: bool) -> dict[str, Any]:
    user_id = await _current_user_id()
    async with SessionLocal() as session:
        strategy = await session.get(Strategy, strategy_id)
        if strategy is None:
            raise PermissionError("strategy_not_found")
        account = await session.get(Account, strategy.account_id)
        if account is None or str(account.user_id) != user_id:
            raise PermissionError("strategy_not_found")
        strategy.is_enabled = enabled
        await session.commit()
        return {"id": str(strategy.id), "is_enabled": strategy.is_enabled}


# ---------------------------------------------------------------------------
# MCP server bootstrap
# ---------------------------------------------------------------------------


def _build_server():
    """Construct the MCP server and register tools.

    Imported lazily because the ``mcp`` package is optional; if it isn't
    installed the rest of DHRUVA still runs, this module just isn't usable.
    """
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError(
            "MCP server requires `pip install mcp`. Add it to your environment "
            "before running `python -m app.mcp.server`."
        ) from exc

    server = Server("dhruva")
    tools: dict[str, callable] = {
        "list_accounts": list_accounts,
        "list_positions": list_positions,
        "list_orders": list_orders,
        "place_order": place_order,
        "list_strategies": list_strategies,
        "toggle_strategy": toggle_strategy,
    }

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name=name, description=fn.__doc__ or name, inputSchema={})
            for name, fn in tools.items()
        ]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        if name not in tools:
            raise ValueError(f"unknown_tool:{name}")
        result = await tools[name](**(arguments or {}))
        import json as _json

        return [TextContent(type="text", text=_json.dumps(result, default=str))]

    return server, stdio_server


async def _http():
    async for client in get_http_client():
        return client
    raise RuntimeError("http_client_unavailable")


async def _redis():
    async for client in get_redis():
        return client
    raise RuntimeError("redis_unavailable")


async def main() -> None:
    configure_logging(level="INFO", env=get_settings().env)
    server, stdio_server = _build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
