"""Telegram bot.

Outbound: ``TelegramNotifier`` sends order/risk/daily-summary messages.
Inbound: ``TelegramBotListener`` long-polls Telegram, handles ``/positions``,
``/orders``, ``/holdings``, ``/pnl``, ``/help``, plus inline approve/reject
buttons on pending ApprovalRequest notifications.

Critical fix vs. prior version: the strings used escaped ``\\n`` (literal
backslash-n) instead of real newlines, so messages rendered as one long line.
All multi-line bodies now use the proper ``\n`` Python string escape.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.execution.approval_service import ApprovalService
from app.db.models.approval import ApprovalRequest
from app.db.models.notification import NotificationConfig, RiskAlert
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.user import User
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org"


@dataclass(frozen=True)
class DailySummary:
    pnl: str
    orders: int
    positions: int


class TelegramNotifier:
    """Outbound-only client. Safe to construct everywhere; if no bot token is
    configured, methods become no-ops and log a warning once at startup.
    """

    def __init__(self, bot_token: str, http: httpx.AsyncClient):
        self._bot_token = bot_token
        self._http = http
        if not bot_token:
            logger.info("telegram.disabled", reason="no_bot_token")

    async def send_text(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        if not self._bot_token:
            return
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            await self._http.post(
                f"{TELEGRAM_API}/bot{self._bot_token}/sendMessage",
                json=payload,
                timeout=10.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("telegram.send_failed", error=str(exc))

    async def send_order_filled(self, chat_id: str, order: Order) -> None:
        text = (
            "<b>Order Filled</b>\n"
            f"<b>ID:</b> <code>{order.id}</code>\n"
            f"<b>Symbol:</b> {order.symbol} ({order.exchange})\n"
            f"<b>Side:</b> {order.side}\n"
            f"<b>Qty:</b> {order.quantity}\n"
            f"<b>Price:</b> {order.price or 'MKT'}\n"
            f"<b>Status:</b> {order.status}"
        )
        await self.send_text(chat_id, text)

    async def send_risk_alert(self, chat_id: str, alert: RiskAlert) -> None:
        text = (
            f"<b>Risk Alert ({alert.severity})</b>\n"
            f"<b>Code:</b> {alert.code}\n"
            f"{alert.message}"
        )
        await self.send_text(chat_id, text)

    async def send_daily_summary(self, chat_id: str, summary: DailySummary) -> None:
        text = (
            "<b>Daily Summary</b>\n"
            f"<b>P&amp;L:</b> {summary.pnl}\n"
            f"<b>Orders:</b> {summary.orders}\n"
            f"<b>Positions:</b> {summary.positions}"
        )
        await self.send_text(chat_id, text)

    async def send_approval_request(
        self, chat_id: str, approval: ApprovalRequest
    ) -> None:
        signal = approval.signal_jsonb
        text = (
            "<b>Approval Required</b>\n"
            f"<b>Symbol:</b> {signal.get('symbol')}\n"
            f"<b>Side:</b> {signal.get('side')}\n"
            f"<b>Qty:</b> {signal.get('quantity')}\n"
            f"<b>Expires:</b> {approval.expires_at.isoformat()}"
        )
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Approve", "callback_data": f"approve:{approval.id}"},
                    {"text": "❌ Reject", "callback_data": f"reject:{approval.id}"},
                ]
            ]
        }
        await self.send_text(chat_id, text, reply_markup=keyboard)


class TelegramBotListener:
    """Long-polls Telegram for incoming messages and dispatches commands.

    Protocol: each authenticated user runs ``/start`` once, copies the chat id
    into the app's notification linking endpoint. From then on, commands sent to
    the bot from that chat are scoped to that user.

    Started/stopped from the FastAPI lifespan (see ``app.main``). If no bot
    token is set, ``run`` exits immediately so dev environments don't churn.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        http: httpx.AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
        notifier: TelegramNotifier,
        approval_service_factory: Callable[[AsyncSession], ApprovalService],
    ):
        self._token = bot_token
        self._http = http
        self._session_factory = session_factory
        self._notifier = notifier
        # The wiring code in main.py provides this factory so the listener can
        # build an ApprovalService bound to the same session it loaded the user
        # with. Keeps the listener free of import-time dependencies.
        self._approval_service_factory = approval_service_factory
        self._stop = asyncio.Event()
        self._offset = 0

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        if not self._token:
            logger.info("telegram.listener.skipped", reason="no_bot_token")
            return
        logger.info("telegram.listener.started")
        while not self._stop.is_set():
            try:
                resp = await self._http.get(
                    f"{TELEGRAM_API}/bot{self._token}/getUpdates",
                    params={"timeout": 25, "offset": self._offset},
                    timeout=30.0,
                )
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001
                logger.warning("telegram.poll_failed", error=str(exc))
                await asyncio.sleep(5)
                continue

            for update in payload.get("result", []):
                self._offset = max(self._offset, update["update_id"] + 1)
                try:
                    if "callback_query" in update:
                        await self._handle_callback(update["callback_query"])
                    elif "message" in update:
                        await self._handle_message(update["message"])
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "telegram.handler_failed",
                        update_id=update.get("update_id"),
                        error=str(exc),
                    )

    # ---- handlers ----------------------------------------------------------

    async def _handle_message(self, message: dict[str, Any]) -> None:
        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return
        cmd, *_rest = text.split()
        cmd = cmd.lower().split("@")[0]

        async with self._session_factory() as session:
            user = await self._lookup_user(session, chat_id)
            if user is None and cmd not in {"/start", "/help"}:
                await self._notifier.send_text(
                    chat_id,
                    "This chat isn't linked to a DHRUVA account yet. Use the "
                    "web app's notification settings to link this chat id: "
                    f"<code>{chat_id}</code>",
                )
                return

            if cmd == "/start" or cmd == "/help":
                await self._notifier.send_text(
                    chat_id,
                    "DHRUVA bot — available commands:\n"
                    "/positions — open positions\n"
                    "/orders — recent orders\n"
                    "/holdings — long-term holdings (coming soon)\n"
                    "/pnl — current P&amp;L\n"
                    "/help — show this message",
                )
                return
            if cmd == "/positions":
                await self._send_positions(chat_id, session, user)
            elif cmd == "/orders":
                await self._send_orders(chat_id, session, user)
            elif cmd == "/pnl":
                await self._send_pnl(chat_id, session, user)
            elif cmd == "/holdings":
                await self._notifier.send_text(chat_id, "Holdings view coming soon.")
            else:
                await self._notifier.send_text(chat_id, "Unknown command. Try /help.")

    async def _handle_callback(self, cq: dict[str, Any]) -> None:
        chat_id = str(cq["message"]["chat"]["id"])
        data = cq.get("data", "")
        if ":" not in data:
            return
        action, approval_id = data.split(":", 1)

        async with self._session_factory() as session:
            user = await self._lookup_user(session, chat_id)
            if user is None:
                return
            approval_svc = self._approval_service_factory(session)
            try:
                if action == "approve":
                    await approval_svc.approve(str(user.id), UUID(approval_id))
                    await self._notifier.send_text(
                        chat_id, f"✅ Approved <code>{approval_id}</code>"
                    )
                elif action == "reject":
                    await approval_svc.reject(str(user.id), UUID(approval_id))
                    await self._notifier.send_text(
                        chat_id, f"❌ Rejected <code>{approval_id}</code>"
                    )
            except Exception as exc:  # noqa: BLE001
                await self._notifier.send_text(chat_id, f"Failed: {exc}")

    # ---- helpers -----------------------------------------------------------

    async def _lookup_user(self, session: AsyncSession, chat_id: str) -> User | None:
        cfg = await session.scalar(
            select(NotificationConfig).where(
                NotificationConfig.channel == "telegram",
                NotificationConfig.destination == chat_id,
                NotificationConfig.is_active.is_(True),
            )
        )
        if cfg is None:
            return None
        return await session.get(User, cfg.user_id)

    async def _send_positions(
        self, chat_id: str, session: AsyncSession, user: User
    ) -> None:
        from app.db.models.account import Account

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        account_ids = [a.id for a in accounts]
        if not account_ids:
            await self._notifier.send_text(chat_id, "No accounts linked.")
            return
        rows = (
            await session.execute(select(Position).where(Position.account_id.in_(account_ids)))
        ).scalars().all()
        if not rows:
            await self._notifier.send_text(chat_id, "No open positions.")
            return
        lines = ["<b>Positions</b>"]
        for p in rows:
            lines.append(
                f"<b>{p.symbol}</b> {p.exchange} qty={p.quantity} avg={p.avg_cost}"
            )
        await self._notifier.send_text(chat_id, "\n".join(lines))

    async def _send_orders(
        self, chat_id: str, session: AsyncSession, user: User
    ) -> None:
        from app.db.models.account import Account

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        account_ids = [a.id for a in accounts]
        if not account_ids:
            await self._notifier.send_text(chat_id, "No accounts linked.")
            return
        recent = (
            await session.execute(
                select(Order)
                .where(Order.account_id.in_(account_ids))
                .order_by(Order.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        if not recent:
            await self._notifier.send_text(chat_id, "No orders yet.")
            return
        lines = ["<b>Recent orders</b>"]
        for o in recent:
            lines.append(
                f"{o.symbol} {o.side} qty={o.quantity} status={o.status}"
            )
        await self._notifier.send_text(chat_id, "\n".join(lines))

    async def _send_pnl(self, chat_id: str, session: AsyncSession, user: User) -> None:
        from app.db.models.account import Account

        accounts = (
            await session.execute(select(Account).where(Account.user_id == user.id))
        ).scalars().all()
        account_ids = [a.id for a in accounts]
        if not account_ids:
            await self._notifier.send_text(chat_id, "No accounts linked.")
            return
        rows = (
            await session.execute(select(Position).where(Position.account_id.in_(account_ids)))
        ).scalars().all()
        realized = sum((p.realized_pnl for p in rows), Decimal("0"))
        await self._notifier.send_text(
            chat_id, f"<b>P&amp;L</b>\nRealized: {realized}"
        )
