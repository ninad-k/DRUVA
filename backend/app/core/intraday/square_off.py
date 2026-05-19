"""Intraday auto square-off service.

Closes ALL intraday (MIS/BO/CO product) positions by 3:15 PM IST.
This prevents overnight holding of intraday positions which would
result in broker-forced square-off at unfavorable prices (3:20-3:25 PM).

Also provides emergency square-off on circuit breaker triggers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time
from typing import Any

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

# Intraday product codes — CNC (delivery) and NRML (carry-forward) are excluded
_INTRADAY_PRODUCTS: frozenset[str] = frozenset({"MIS", "BO", "CO"})

# IST = UTC+5:30
_IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60

# Default auto square-off time: 15:15 IST
_DEFAULT_SQUARE_OFF_TIME = time(15, 15, 0)

# IST weekday indices (Monday=0 … Friday=4)
_WEEKDAYS = frozenset(range(5))


def _ist_now() -> datetime:
    """Return current IST datetime as a naive datetime (no tzinfo)."""
    utc_ts = utcnow().timestamp()
    ist_ts = utc_ts + _IST_OFFSET_SECONDS
    return datetime.utcfromtimestamp(ist_ts)


class AutoSquareOff:
    """Automatically closes all intraday positions at 3:15 PM IST.

    Designed to be wired into the APScheduler cron job scheduler so that it
    fires Monday–Friday at 15:15 IST without any manual intervention.

    It also exposes an emergency square-off path for circuit-breaker events.

    Args:
        execution_service: App's :class:`~app.core.execution.execution_service.ExecutionService`
            instance (duck-typed to avoid import-time coupling).
        account_id: The trading account whose intraday positions will be closed.
        square_off_time: IST wall-clock time at which the scheduled job fires.
            Defaults to 15:15.
    """

    def __init__(
        self,
        execution_service: Any,
        account_id: str,
        square_off_time: time = _DEFAULT_SQUARE_OFF_TIME,
    ) -> None:
        self._execution_service = execution_service
        self.account_id = account_id
        self.square_off_time = square_off_time

        logger.info(
            "auto_square_off.init",
            account_id=account_id,
            square_off_time=square_off_time.isoformat(),
        )

    # ---------------------------------------------------------------------- public

    async def square_off_all_intraday(self, user_id: str) -> list[Any]:
        """Close every open intraday (MIS/BO/CO) position for the account.

        Args:
            user_id: Authenticated user id that will appear in the audit trail.

        Returns:
            List of :class:`~app.db.models.order.Order` objects representing
            the closing orders placed.
        """
        positions = await self.get_intraday_positions()
        if not positions:
            logger.info(
                "auto_square_off.no_positions",
                account_id=self.account_id,
                reason="normal_square_off",
            )
            return []

        closed_orders: list[Any] = []
        errors: list[str] = []

        for position in positions:
            symbol = getattr(position, "symbol", str(position))
            try:
                order = await self._execution_service.close_position(
                    user_id,
                    self.account_id,
                    symbol,
                )
                closed_orders.append(order)
                logger.info(
                    "auto_square_off.position_closed",
                    symbol=symbol,
                    account_id=self.account_id,
                )
            except Exception as exc:  # noqa: BLE001
                error_msg = f"{symbol}: {exc}"
                errors.append(error_msg)
                logger.error(
                    "auto_square_off.close_failed",
                    symbol=symbol,
                    account_id=self.account_id,
                    error=str(exc),
                )

        await self._notify_square_off(
            positions_closed=len(closed_orders),
            reason=f"scheduled_3:15PM_IST (errors={len(errors)})",
        )

        if errors:
            logger.error(
                "auto_square_off.partial_failure",
                account_id=self.account_id,
                failed_symbols=errors,
            )

        return closed_orders

    async def get_intraday_positions(self) -> list[Any]:
        """Return all open positions whose product is in {MIS, BO, CO}.

        Excludes CNC (delivery) and NRML (overnight futures) positions.
        """
        try:
            all_positions = await self._execution_service.list_positions(self.account_id)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "auto_square_off.fetch_positions_failed",
                account_id=self.account_id,
                error=str(exc),
            )
            return []

        intraday = [
            p
            for p in all_positions
            if (
                getattr(p, "product", None) in _INTRADAY_PRODUCTS
                and getattr(p, "quantity", 0) != 0
            )
        ]

        logger.debug(
            "auto_square_off.intraday_positions",
            account_id=self.account_id,
            count=len(intraday),
            total=len(all_positions),
        )
        return intraday

    async def emergency_square_off(self, user_id: str, reason: str) -> list[Any]:
        """Immediately flatten all intraday positions.

        Triggered by circuit-breaker events (e.g. index halts, extreme drawdown).
        Logs at ERROR level and attempts to close every position even if some fail.

        Args:
            user_id: User id for audit trail.
            reason: Human-readable trigger description (e.g. "circuit_breaker_halt").

        Returns:
            List of closing orders placed (same shape as square_off_all_intraday).
        """
        logger.error(
            "auto_square_off.EMERGENCY",
            account_id=self.account_id,
            reason=reason,
            ts=utcnow().isoformat(),
        )

        positions = await self.get_intraday_positions()
        if not positions:
            logger.warning(
                "auto_square_off.emergency_no_positions",
                account_id=self.account_id,
                reason=reason,
            )
            return []

        # Fan out closes concurrently for minimum latency in emergency
        async def _close_one(position: Any) -> Any | None:
            symbol = getattr(position, "symbol", str(position))
            try:
                order = await self._execution_service.close_position(
                    user_id,
                    self.account_id,
                    symbol,
                )
                logger.error(  # ERROR level so it appears prominently in dashboards
                    "auto_square_off.emergency_closed",
                    symbol=symbol,
                    account_id=self.account_id,
                    reason=reason,
                )
                return order
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "auto_square_off.emergency_close_failed",
                    symbol=symbol,
                    account_id=self.account_id,
                    reason=reason,
                    error=str(exc),
                )
                return None

        results = await asyncio.gather(*[_close_one(p) for p in positions])
        closed_orders = [r for r in results if r is not None]

        await self._notify_square_off(
            positions_closed=len(closed_orders),
            reason=f"EMERGENCY: {reason}",
        )
        return closed_orders

    def schedule_daily_square_off(self, scheduler: Any) -> None:
        """Register an APScheduler cron job at the configured time, Mon–Fri IST.

        Args:
            scheduler: An :class:`apscheduler.schedulers.asyncio.AsyncIOScheduler`
                instance (or compatible scheduler).

        Note:
            The job id is stable (``auto_square_off_{account_id}``) so
            re-registering is safe — APScheduler will replace the existing job.
        """
        job_id = f"auto_square_off_{self.account_id}"

        scheduler.add_job(
            self._scheduled_square_off,
            trigger="cron",
            hour=self.square_off_time.hour,
            minute=self.square_off_time.minute,
            second=self.square_off_time.second,
            day_of_week="mon-fri",
            timezone="Asia/Kolkata",
            id=job_id,
            replace_existing=True,
            misfire_grace_time=60,  # allow up to 60 s late if system was busy
        )
        logger.info(
            "auto_square_off.job_scheduled",
            account_id=self.account_id,
            job_id=job_id,
            time=self.square_off_time.isoformat(),
        )

    def is_square_off_time(self) -> bool:
        """Return True if the current IST time is >= 3:15 PM on a weekday."""
        now_ist = _ist_now()
        if now_ist.weekday() not in _WEEKDAYS:
            return False
        return now_ist.time() >= self.square_off_time

    # ---------------------------------------------------------------------- private

    async def _scheduled_square_off(self) -> None:
        """APScheduler entry-point — uses a system user id for the audit trail."""
        logger.info(
            "auto_square_off.scheduled_triggered",
            account_id=self.account_id,
            ist_time=_ist_now().time().isoformat(),
        )
        system_user_id = f"system:auto_square_off:{self.account_id}"
        await self.square_off_all_intraday(user_id=system_user_id)

    async def _notify_square_off(self, positions_closed: int, reason: str) -> None:
        """Log a summary and emit a Telegram notification if wired up.

        In production, inject a TelegramNotifier instance via the constructor
        and call send_text here. This default implementation logs only.
        """
        logger.info(
            "auto_square_off.notification",
            account_id=self.account_id,
            positions_closed=positions_closed,
            reason=reason,
        )
        # Telegram notification hook — override by subclassing or by injecting
        # a notifier at construction time and calling notifier.send_text().
        # Example wiring (not done here to keep this module dependency-free):
        #   if self._telegram_notifier and self._chat_id:
        #       await self._telegram_notifier.send_text(
        #           self._chat_id,
        #           f"<b>Auto Square-Off Complete</b>\n"
        #           f"Positions closed: {positions_closed}\n"
        #           f"Reason: {reason}"
        #       )
