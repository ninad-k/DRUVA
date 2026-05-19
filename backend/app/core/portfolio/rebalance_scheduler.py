"""Drift-based portfolio rebalance scheduler.

Checks portfolio drift against target allocation every market close.
If any position drifts > threshold (default 5%), raises a rebalance approval request.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.core.execution.execution_service import ExecutionService
    from app.core.notifications.email import EmailNotifier

logger = get_logger(__name__)

# NSE holidays for 2026 (hardcoded as required)
_NSE_HOLIDAYS_2026: frozenset[str] = frozenset({
    "2026-01-26",  # Republic Day
    "2026-02-18",  # Mahashivratri
    "2026-03-19",  # Holi
    "2026-03-20",  # Holi
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-04-15",  # Gudi Padwa / Ugadi
    "2026-05-01",  # Maharashtra Day
    "2026-06-19",  # Id-ul-Adha (Bakri Id)
    "2026-07-17",  # Muharram
    "2026-08-17",  # Parsi New Year
    "2026-09-16",  # Milad-un-Nabi
    "2026-10-02",  # Mahatma Gandhi Jayanti
    "2026-10-20",  # Diwali (Laxmi Puja)
    "2026-10-21",  # Diwali (Balipratipada)
    "2026-11-04",  # Guru Nanak Jayanti
    "2026-11-25",  # Christmas Eve (observed)
    "2026-12-25",  # Christmas
})

# Brokerage constants
_BROKERAGE_FLAT = Decimal("20")          # ₹20 per order (Zerodha-style)
_BROKERAGE_PCT = Decimal("0.0003")       # 0.03% of turnover
_STT_SELL_PCT = Decimal("0.001")         # 0.1% STT on sell-side delivery


@dataclass
class DriftResult:
    """Drift analysis for a single symbol."""

    symbol: str
    current_pct: float
    target_pct: float
    drift_pct: float          # positive = overweight, negative = underweight
    action: str               # "BUY", "SELL", or "HOLD"


class RebalanceScheduler:
    """Periodic drift checker and rebalance trigger.

    Compares live portfolio weights to a target allocation map.
    When any symbol drifts beyond ``drift_threshold_pct``, sends an
    approval request via the notifier and optionally places trades.
    """

    def __init__(
        self,
        execution_service: ExecutionService,
        notifier: EmailNotifier | None,
        drift_threshold_pct: float = 5.0,
    ) -> None:
        self._execution = execution_service
        self._notifier = notifier
        self._threshold = drift_threshold_pct

    async def check_drift(
        self,
        account_id: str,
        target_allocation: dict[str, float],
    ) -> list[DriftResult]:
        """Compare live holdings weights to target and return drift for every symbol.

        Args:
            account_id: UUID string of the account to inspect.
            target_allocation: ``{symbol: pct}`` where pct is 0–100.

        Returns:
            A list of DriftResult for all symbols in either current or target set.
        """
        import uuid

        positions = await self._execution.list_positions(uuid.UUID(account_id))

        # Build current value map
        total_value = sum(
            (p.avg_cost or Decimal("0")) * abs(p.quantity) for p in positions
        )

        current_weights: dict[str, float] = {}
        if total_value > 0:
            for pos in positions:
                notional = (pos.avg_cost or Decimal("0")) * abs(pos.quantity)
                current_weights[pos.symbol] = float(notional / total_value * 100)

        all_symbols = set(current_weights) | set(target_allocation)
        results: list[DriftResult] = []

        for symbol in sorted(all_symbols):
            current_pct = current_weights.get(symbol, 0.0)
            target_pct = target_allocation.get(symbol, 0.0)
            drift = current_pct - target_pct

            if abs(drift) < 0.01:
                action = "HOLD"
            elif drift < 0:
                action = "BUY"   # underweight → buy more
            else:
                action = "SELL"  # overweight → trim

            results.append(
                DriftResult(
                    symbol=symbol,
                    current_pct=current_pct,
                    target_pct=target_pct,
                    drift_pct=drift,
                    action=action,
                )
            )

        return results

    async def trigger_if_needed(
        self,
        account_id: str,
        target_allocation: dict[str, float],
    ) -> bool:
        """Run drift check and send approval request if threshold is breached.

        Returns:
            True if a rebalance approval request was dispatched, False otherwise.
        """
        if not self._is_market_open():
            logger.info("rebalance.skipped", reason="market_closed_or_holiday")
            return False

        drifts = await self.check_drift(account_id, target_allocation)
        breached = [d for d in drifts if abs(d.drift_pct) >= self._threshold]

        if not breached:
            logger.info(
                "rebalance.no_drift",
                max_drift=max((abs(d.drift_pct) for d in drifts), default=0.0),
                threshold=self._threshold,
            )
            return False

        logger.warning(
            "rebalance.drift_breached",
            symbols=[d.symbol for d in breached],
            max_drift=max(abs(d.drift_pct) for d in breached),
            threshold=self._threshold,
        )

        if self._notifier:
            summary = {
                "account_id": account_id,
                "breached_symbols": [d.symbol for d in breached],
                "checked_at": utcnow().isoformat(),
                "threshold_pct": self._threshold,
            }
            await self._notifier.send(
                to=[],  # caller wires in recipient list via partial/subclass
                subject="[DRUVA] Portfolio Rebalance Required",
                body_html=self._render_drift_email(drifts, breached),
            )

        return True

    async def estimate_rebalance_cost(
        self,
        drifts: list[DriftResult],
        portfolio_value: float,
    ) -> float:
        """Estimate total brokerage + STT for rebalancing the given drift list.

        Brokerage per order = min(₹20 flat, 0.03% of turnover).
        STT on SELL side = 0.1% of sell turnover (delivery).

        Returns total estimated cost in INR (as float for display).
        """
        total_cost = Decimal("0")
        pv = Decimal(str(portfolio_value))

        for drift in drifts:
            if drift.action == "HOLD":
                continue

            trade_pct = Decimal(str(abs(drift.drift_pct))) / Decimal("100")
            turnover = pv * trade_pct

            brokerage_pct_val = turnover * _BROKERAGE_PCT
            brokerage = min(_BROKERAGE_FLAT, brokerage_pct_val)
            total_cost += brokerage

            if drift.action == "SELL":
                stt = turnover * _STT_SELL_PCT
                total_cost += stt

        return float(total_cost)

    def schedule_daily(
        self,
        scheduler: AsyncIOScheduler,
        account_id: str,
        target_allocation: dict[str, float],
    ) -> None:
        """Register a daily APScheduler job at 3:35 PM IST on NSE trading days.

        3:35 PM IST = 10:05 UTC.
        The job itself re-checks whether the day is a holiday before acting.
        """
        scheduler.add_job(
            self.trigger_if_needed,
            trigger="cron",
            hour=10,
            minute=5,
            day_of_week="mon-fri",
            timezone="UTC",
            args=[account_id, target_allocation],
            id=f"rebalance_drift_check_{account_id}",
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(
            "rebalance.scheduler_registered",
            account_id=account_id,
            cron="10:05 UTC (15:35 IST) Mon-Fri",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _is_market_open(self) -> bool:
        """Return True if today is a weekday and not an NSE 2026 holiday."""
        today = utcnow().date()
        if today.weekday() >= 5:  # Sat=5, Sun=6
            return False
        return today.isoformat() not in _NSE_HOLIDAYS_2026

    def _render_drift_email(
        self,
        all_drifts: list[DriftResult],
        breached: list[DriftResult],
    ) -> str:
        """Build a simple HTML table summarising drift for the notification email."""
        rows_html = ""
        for d in all_drifts:
            color = "#ef4444" if abs(d.drift_pct) >= self._threshold else "#a1a1aa"
            rows_html += (
                f"<tr>"
                f"<td style='padding:4px 8px;'>{d.symbol}</td>"
                f"<td style='padding:4px 8px;'>{d.current_pct:.2f}%</td>"
                f"<td style='padding:4px 8px;'>{d.target_pct:.2f}%</td>"
                f"<td style='padding:4px 8px;color:{color};font-weight:600;'>"
                f"{d.drift_pct:+.2f}%</td>"
                f"<td style='padding:4px 8px;'>{d.action}</td>"
                f"</tr>"
            )
        return (
            "<p>Portfolio drift has exceeded the configured threshold. "
            f"<strong>{len(breached)} symbol(s)</strong> require rebalancing.</p>"
            "<table border='0' cellpadding='0' cellspacing='0' "
            "style='border-collapse:collapse;width:100%;font-size:13px;'>"
            "<thead><tr style='background:#3f3f46;'>"
            "<th style='padding:8px;text-align:left;'>Symbol</th>"
            "<th style='padding:8px;text-align:left;'>Current %</th>"
            "<th style='padding:8px;text-align:left;'>Target %</th>"
            "<th style='padding:8px;text-align:left;'>Drift</th>"
            "<th style='padding:8px;text-align:left;'>Action</th>"
            "</tr></thead>"
            f"<tbody>{rows_html}</tbody>"
            "</table>"
        )
