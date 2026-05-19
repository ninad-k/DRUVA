"""Bridges RegimeTraderStrategy predictions to DRUVA's ExecutionService.

On each new daily bar:
  1. Run RegimeTraderStrategy.predict()
  2. Apply India VIX modifier to regime confidence
  3. Check circuit breakers (2%/3%/10% drawdown logic)
  4. If signal is BUY/SELL and persistence >= 3 bars: route to ExecutionService
  5. Send Telegram + email notifications on regime change
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
import pandas as pd

from app.core.market.india_vix import VixReading, get_vix_with_fallback, vix_to_regime_modifier
from app.infrastructure.logging import get_logger
from app.strategies.ml.regime_trader.strategy import RegimeTraderStrategy
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.core.execution.execution_service import ExecutionService
    from app.core.notifications.email import EmailNotifier
    from app.core.notifications.telegram import TelegramNotifier
    from app.strategies.ml.base_ml import Prediction

logger = get_logger(__name__)

# Path where the lock file is written when the 10% drawdown circuit trips
_BACKEND_DIR = Path(__file__).resolve().parents[3]  # backend/
_LOCK_FILE = _BACKEND_DIR / "DRUVA.lock"

# Circuit breaker thresholds
_CB_HALF_CUT_PCT = -2.0    # -2% daily P&L → halve all sizes
_CB_FULL_CLOSE_PCT = -3.0  # -3% daily P&L → close all positions
_CB_LOCK_DRAWDOWN_PCT = -10.0  # -10% drawdown from peak → lock all trading

CircuitStatus = Literal["normal", "half_cut", "full_close", "locked"]


@dataclass
class CircuitBreakerState:
    """Current circuit breaker status for the executor."""

    status: CircuitStatus
    triggered_at: datetime | None
    daily_loss_pct: float
    peak_drawdown_pct: float


@dataclass
class RegimeExecutor:
    """Orchestrates RegimeTrader signals through VIX adjustment, circuit breakers, and execution.

    One instance per account. Not thread-safe — call ``run_daily_bar`` serially.
    """

    execution_service: ExecutionService
    strategy: RegimeTraderStrategy
    telegram_notifier: TelegramNotifier | None
    email_notifier: EmailNotifier | None
    account_id: str
    telegram_chat_id: str = ""
    alert_emails: list[str] = field(default_factory=list)

    # Runtime state (not persisted — resets on restart)
    _last_regime: str = field(default="", init=False, repr=False)
    _http_client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    # ── Main entry point ───────────────────────────────────────────────────

    async def run_daily_bar(self, ohlcv: pd.DataFrame) -> dict:
        """Process one daily OHLCV bar through the full regime-execution pipeline.

        Steps:
          1. Check lock file — abort immediately if locked.
          2. Fetch India VIX.
          3. Run strategy prediction on provided OHLCV.
          4. Apply VIX modifier to adjust allocation.
          5. Check circuit breakers.
          6. If signal warrants action and not blocked, send to ExecutionService.
          7. Notify on regime change.

        Args:
            ohlcv: DataFrame with columns [open, high, low, close, volume].

        Returns:
            dict summarising the run: signal, regime, vix, circuit_status, executed.
        """
        if self.is_locked():
            logger.error("regime_executor.locked", lock_file=str(_LOCK_FILE))
            return {"executed": False, "reason": "trading_locked", "lock_file": str(_LOCK_FILE)}

        client = await self._get_http_client()
        vix_reading = await get_vix_with_fallback(client)

        # Build feature matrix from OHLCV
        features = self.strategy.build_features(self._ohlcv_to_candles(ohlcv))
        prediction: Prediction = self.strategy.predict(features)

        meta = prediction.meta or {}
        old_regime = self._last_regime
        new_regime = meta.get("regime_name", "Unknown")
        persistence = meta.get("persistence_bars", 0)
        confidence = float(meta.get("confidence", 0.0))

        # Apply VIX modifier
        adjusted = await self._apply_vix_modifier(prediction, vix_reading)
        adjusted_allocation = adjusted.get("allocation_pct", meta.get("allocation_pct", 50.0))
        adjusted_confidence = adjusted.get("confidence", confidence)

        # Circuit breaker evaluation (requires portfolio value — use placeholder 0
        # for the allocation step; real P&L check happens via positions below)
        portfolio_value, daily_pnl, peak_value = await self._fetch_portfolio_metrics()
        cb_state = await self._check_circuit_breakers(portfolio_value, peak_value, daily_pnl)

        executed = False
        exec_summary: dict = {}

        signal = prediction.signal
        should_execute = (
            signal in ("BUY", "SELL")
            and persistence >= 3
            and not meta.get("flicker_warning", False)
            and cb_state.status == "normal"
        )

        if cb_state.status == "full_close":
            await self._close_all_positions()
            exec_summary = {"action": "full_close", "reason": "circuit_breaker_3pct"}
            executed = True
        elif cb_state.status == "locked":
            self._write_lock_file(
                reason="drawdown_10pct",
                peak_drawdown_pct=cb_state.peak_drawdown_pct,
            )
            await self._notify_circuit_breaker(cb_state)
        elif cb_state.status == "half_cut" and should_execute:
            exec_summary = await self._execute_signal(
                signal=signal,
                allocation_pct=adjusted_allocation * 0.5,  # halved
                meta=adjusted,
            )
            executed = bool(exec_summary)
        elif should_execute:
            exec_summary = await self._execute_signal(
                signal=signal,
                allocation_pct=adjusted_allocation,
                meta=adjusted,
            )
            executed = bool(exec_summary)

        # Regime change notification
        if new_regime and new_regime != old_regime:
            self._last_regime = new_regime
            await self._notify_regime_change(old_regime, new_regime, adjusted)

        result = {
            "executed": executed,
            "signal": signal,
            "regime": new_regime,
            "regime_id": meta.get("regime_id"),
            "confidence": adjusted_confidence,
            "allocation_pct": adjusted_allocation,
            "persistence_bars": persistence,
            "flicker_warning": meta.get("flicker_warning", False),
            "vix": vix_reading.value,
            "vix_modifier": vix_to_regime_modifier(vix_reading.value),
            "circuit_status": cb_state.status,
            "daily_loss_pct": cb_state.daily_loss_pct,
            "exec_summary": exec_summary,
            "ts": utcnow().isoformat(),
        }
        logger.info("regime_executor.run_complete", **{k: v for k, v in result.items()
                                                        if k != "exec_summary"})
        return result

    # ── Circuit breakers ───────────────────────────────────────────────────

    async def _check_circuit_breakers(
        self,
        portfolio_value: float,
        peak_value: float,
        daily_pnl: float,
    ) -> CircuitBreakerState:
        """Evaluate all three circuit breaker tiers.

        Tier 1 — half_cut: daily P&L <= -2%.
        Tier 2 — full_close: daily P&L <= -3%.
        Tier 3 — locked: drawdown from peak >= 10%.
        """
        if portfolio_value <= 0:
            return CircuitBreakerState(
                status="normal",
                triggered_at=None,
                daily_loss_pct=0.0,
                peak_drawdown_pct=0.0,
            )

        daily_loss_pct = (daily_pnl / portfolio_value) * 100.0
        peak_drawdown_pct = 0.0
        if peak_value > 0:
            peak_drawdown_pct = ((portfolio_value - peak_value) / peak_value) * 100.0

        # Tier 3 — lock (hardest)
        if peak_drawdown_pct <= _CB_LOCK_DRAWDOWN_PCT:
            logger.critical(
                "circuit_breaker.locked",
                peak_drawdown_pct=peak_drawdown_pct,
                threshold=_CB_LOCK_DRAWDOWN_PCT,
            )
            return CircuitBreakerState(
                status="locked",
                triggered_at=utcnow(),
                daily_loss_pct=daily_loss_pct,
                peak_drawdown_pct=peak_drawdown_pct,
            )

        # Tier 2 — full close
        if daily_loss_pct <= _CB_FULL_CLOSE_PCT:
            logger.error(
                "circuit_breaker.full_close",
                daily_loss_pct=daily_loss_pct,
                threshold=_CB_FULL_CLOSE_PCT,
            )
            return CircuitBreakerState(
                status="full_close",
                triggered_at=utcnow(),
                daily_loss_pct=daily_loss_pct,
                peak_drawdown_pct=peak_drawdown_pct,
            )

        # Tier 1 — half cut
        if daily_loss_pct <= _CB_HALF_CUT_PCT:
            logger.warning(
                "circuit_breaker.half_cut",
                daily_loss_pct=daily_loss_pct,
                threshold=_CB_HALF_CUT_PCT,
            )
            return CircuitBreakerState(
                status="half_cut",
                triggered_at=utcnow(),
                daily_loss_pct=daily_loss_pct,
                peak_drawdown_pct=peak_drawdown_pct,
            )

        return CircuitBreakerState(
            status="normal",
            triggered_at=None,
            daily_loss_pct=daily_loss_pct,
            peak_drawdown_pct=peak_drawdown_pct,
        )

    # ── VIX modifier ──────────────────────────────────────────────────────

    async def _apply_vix_modifier(
        self,
        prediction: Prediction,
        vix_reading: VixReading,
    ) -> dict:
        """Adjust allocation_pct up/down based on India VIX regime modifier.

        VIX modifier of +2 → boost allocation by up to 10 pp.
        VIX modifier of -2 → cut allocation by up to 20 pp.
        Confidence is also dampened when VIX indicates extreme fear.
        """
        meta = dict(prediction.meta or {})
        modifier = vix_to_regime_modifier(vix_reading.value)
        original_alloc: float = float(meta.get("allocation_pct", 50.0))
        original_conf: float = float(meta.get("confidence", 0.0))

        # Each modifier step = 5 pp change in allocation
        adjustment_pp = modifier * 5.0
        adjusted_alloc = max(0.0, min(100.0, original_alloc + adjustment_pp))

        # Dampen confidence in extreme fear
        conf_dampen = max(0.0, 1.0 + modifier * 0.05) if modifier < 0 else 1.0
        adjusted_conf = min(1.0, original_conf * conf_dampen)

        meta["allocation_pct"] = adjusted_alloc
        meta["confidence"] = adjusted_conf
        meta["vix_value"] = vix_reading.value
        meta["vix_modifier"] = modifier
        meta["allocation_pct_original"] = original_alloc

        logger.debug(
            "regime_executor.vix_applied",
            vix=vix_reading.value,
            modifier=modifier,
            allocation_before=original_alloc,
            allocation_after=adjusted_alloc,
        )
        return meta

    # ── Notifications ─────────────────────────────────────────────────────

    async def _notify_regime_change(
        self,
        old_regime: str,
        new_regime: str,
        meta: dict,
    ) -> None:
        """Send Telegram + email on regime change."""
        confidence: float = float(meta.get("confidence", 0.0))
        allocation_pct: float = float(meta.get("allocation_pct", 50.0))

        # Telegram
        if self.telegram_notifier and self.telegram_chat_id:
            text = (
                "<b>Regime Change</b>\n"
                f"<b>From:</b> {old_regime or '—'}\n"
                f"<b>To:</b> {new_regime}\n"
                f"<b>Confidence:</b> {confidence:.1%}\n"
                f"<b>New Allocation:</b> {allocation_pct:.1f}%\n"
                f"<b>VIX:</b> {meta.get('vix_value', '—')}"
            )
            await self.telegram_notifier.send_text(self.telegram_chat_id, text)

        # Email
        if self.email_notifier and self.alert_emails:
            await self.email_notifier.send_regime_change(
                to=self.alert_emails,
                old_regime=old_regime or "—",
                new_regime=new_regime,
                confidence=confidence,
                allocation_pct=allocation_pct,
            )

    async def _notify_circuit_breaker(self, cb_state: CircuitBreakerState) -> None:
        """Send Telegram + email for circuit breaker events."""
        trigger = f"status={cb_state.status}"

        if self.telegram_notifier and self.telegram_chat_id:
            text = (
                "<b>⚠ CIRCUIT BREAKER TRIGGERED</b>\n"
                f"<b>Status:</b> {cb_state.status}\n"
                f"<b>Daily Loss:</b> {cb_state.daily_loss_pct:.2f}%\n"
                f"<b>Peak Drawdown:</b> {cb_state.peak_drawdown_pct:.2f}%"
            )
            await self.telegram_notifier.send_text(self.telegram_chat_id, text)

        if self.email_notifier and self.alert_emails:
            await self.email_notifier.send_circuit_breaker_alert(
                to=self.alert_emails,
                trigger=trigger,
                portfolio_value=0.0,
                loss_pct=abs(cb_state.daily_loss_pct),
            )

    # ── Lock file ─────────────────────────────────────────────────────────

    def _write_lock_file(
        self,
        reason: str,
        peak_drawdown_pct: float,
    ) -> None:
        """Write DRUVA.lock JSON file to halt all trading.

        The file's existence is the lock signal — any component can call
        ``is_locked()`` to check it.
        """
        payload = {
            "locked_at": utcnow().isoformat(),
            "reason": reason,
            "peak_drawdown_pct": peak_drawdown_pct,
            "account_id": self.account_id,
            "written_by": "RegimeExecutor._write_lock_file",
        }
        _LOCK_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.critical(
            "regime_executor.lock_written",
            lock_file=str(_LOCK_FILE),
            reason=reason,
            peak_drawdown_pct=peak_drawdown_pct,
        )

    def is_locked(self) -> bool:
        """Return True if DRUVA.lock exists on disk."""
        return _LOCK_FILE.exists()

    # ── Internals ─────────────────────────────────────────────────────────

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Return or lazily create a shared async HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient()
        return self._http_client

    async def _fetch_portfolio_metrics(self) -> tuple[float, float, float]:
        """Return (portfolio_value, daily_pnl, peak_value).

        Queries live positions via ExecutionService. Peak value is not persisted
        across restarts — starts fresh each process lifecycle.
        """
        import uuid

        positions = await self.execution_service.list_positions(uuid.UUID(self.account_id))
        portfolio_value = sum(
            float((p.avg_cost or Decimal("0")) * abs(p.quantity)) for p in positions
        )
        daily_pnl = sum(float(p.realized_pnl or Decimal("0")) for p in positions)

        # Track peak naively in-process (no DB persistence)
        current_peak: float = getattr(self, "_peak_value", portfolio_value)
        if portfolio_value > current_peak:
            current_peak = portfolio_value
            object.__setattr__(self, "_peak_value", current_peak)  # type: ignore[arg-type]

        return portfolio_value, daily_pnl, current_peak

    async def _close_all_positions(self) -> None:
        """Close every open position on the account (circuit breaker full-close)."""
        import uuid

        positions = await self.execution_service.list_positions(uuid.UUID(self.account_id))
        for pos in positions:
            if pos.quantity == 0:
                continue
            try:
                await self.execution_service.close_position(
                    user_id=self.account_id,
                    account_id=uuid.UUID(self.account_id),
                    symbol=pos.symbol,
                )
                logger.info(
                    "regime_executor.position_closed",
                    symbol=pos.symbol,
                    reason="circuit_breaker",
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "regime_executor.close_failed",
                    symbol=pos.symbol,
                    error=str(exc),
                )

    async def _execute_signal(
        self,
        signal: str,
        allocation_pct: float,
        meta: dict,
    ) -> dict:
        """Translate a regime signal into a concrete order via ExecutionService.

        Uses NIFTY 50 ETF (NIFTYBEES) as the default instrument for regime
        expression. Real deployments should wire in the correct instrument map.
        """
        from app.core.execution.models import SmartOrderRequest

        # Default instrument — override via strategy parameters
        instrument = meta.get("instrument", "NIFTYBEES")
        exchange = meta.get("exchange", "NSE")

        # Calculate target quantity from allocation %
        # Without live price here, we use a notional unit; real impl needs price feed
        target_qty = Decimal(str(int(allocation_pct)))  # 1 share per allocation %

        if signal == "BUY":
            pass  # target_qty stays as is
        elif signal == "SELL":
            target_qty = Decimal("0")

        try:
            req = SmartOrderRequest(
                account_id=self.account_id,  # type: ignore[arg-type]
                symbol=instrument,
                exchange=exchange,
                target_quantity=target_qty,
                product="CNC",
            )
            order = await self.execution_service.smart_order(
                user_id=self.account_id,
                req=req,
            )
            return {
                "order_id": str(order.id),
                "symbol": instrument,
                "signal": signal,
                "target_qty": str(target_qty),
                "status": order.status,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "regime_executor.execution_failed",
                signal=signal,
                instrument=instrument,
                error=str(exc),
            )
            return {}

    @staticmethod
    def _ohlcv_to_candles(ohlcv: pd.DataFrame) -> list:
        """Convert a pandas OHLCV DataFrame to a lightweight candle list.

        The strategy's ``build_features`` only needs ``.close`` and ``.volume``
        attributes, so we use a simple namespace object.
        """
        from types import SimpleNamespace

        candles = []
        for _, row in ohlcv.iterrows():
            candles.append(
                SimpleNamespace(
                    open=Decimal(str(row.get("open", 0))),
                    high=Decimal(str(row.get("high", 0))),
                    low=Decimal(str(row.get("low", 0))),
                    close=Decimal(str(row.get("close", 0))),
                    volume=Decimal(str(row.get("volume", 0))),
                )
            )
        return candles
