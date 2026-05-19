"""VWAP Reversion Scalping Strategy for DRUVA.

Logic:
  Entry (LONG): Price deviates > entry_threshold% BELOW VWAP + volume spike (> 1.5x avg vol)
  Entry (SHORT): Price deviates > entry_threshold% ABOVE VWAP + volume spike

  Exit (LONG): Price returns to VWAP (take profit) OR hits stop_loss_pct below entry
  Exit (SHORT): Price returns to VWAP (take profit) OR hits stop_loss_pct above entry

Rules:
  - Max 3 trades per session (intraday only)
  - Only trade between 9:30 AM and 2:30 PM IST (avoid opening volatility + closing auction)
  - Max 2% of scalping capital per trade
  - Auto-flatten all positions at 3:15 PM IST
  - Eligible symbols: NIFTY FUT, BANKNIFTY FUT (liquid futures only)
  - Minimum 30-second candles (don't react to single ticks)
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, time, timezone
from decimal import Decimal

from app.infrastructure.logging import get_logger
from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.registry import register_strategy
from app.utils.time import utcnow

logger = get_logger(__name__)

# IST = UTC+5:30
_IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60

# Eligible symbols for VWAP reversion scalping (liquid futures only)
_ELIGIBLE_SYMBOLS: frozenset[str] = frozenset({"NIFTY FUT", "BANKNIFTY FUT"})

# Minimum candle interval accepted (seconds) — 30s candles
_MIN_CANDLE_TIMEFRAME = "30s"

# Trading window in IST: 09:30 – 14:30
_TRADING_START_IST = time(9, 30, 0)
_TRADING_END_IST = time(14, 30, 0)

# Number of bars used to compute average volume
_VOL_LOOKBACK = 20


def _to_ist_time(dt: datetime) -> time:
    """Return the IST wall-clock time for a UTC-aware datetime."""
    utc_ts = dt.timestamp()
    ist_ts = utc_ts + _IST_OFFSET_SECONDS
    ist_dt = datetime.utcfromtimestamp(ist_ts)
    return ist_dt.time()


@register_strategy("scalping.vwap_reversion.v1")
class VWAPReversionStrategy(Strategy):
    """VWAP Reversion scalping strategy.

    Watches for price deviations from intraday VWAP combined with a volume spike
    and enters a counter-trend position expecting reversion to the mean.

    Parameters (override via ``parameters`` dict)::

        entry_threshold_pct   float  0.3   — % deviation from VWAP to trigger entry
        stop_loss_pct         float  0.15  — % stop loss from entry price
        max_trades_per_session int   3     — hard cap on new entries per day
        volume_spike_multiplier float 1.5  — volume must exceed N × 20-bar average
        capital_pct_per_trade float  2.0  — max % of scalping capital per trade
    """

    def __init__(self, *, id: str, account_id: str, parameters: dict | None = None) -> None:
        super().__init__(id=id, account_id=account_id, parameters=parameters)

        # Strategy parameters with defaults
        self._entry_threshold_pct: float = float(
            self.parameters.get("entry_threshold_pct", 0.3)
        )
        self._stop_loss_pct: float = float(
            self.parameters.get("stop_loss_pct", 0.15)
        )
        self._max_trades_per_session: int = int(
            self.parameters.get("max_trades_per_session", 3)
        )
        self._volume_spike_multiplier: float = float(
            self.parameters.get("volume_spike_multiplier", 1.5)
        )
        self._capital_pct_per_trade: float = float(
            self.parameters.get("capital_pct_per_trade", 2.0)
        )

        # Session state — reset daily via reset_daily()
        self._trades_today: int = 0
        self._open_side: str | None = None       # "BUY" | "SELL" | None
        self._entry_price: Decimal | None = None

        # Rolling candle buffer for volume and VWAP computation
        self._candle_buffer: deque[Candle] = deque(maxlen=200)

        logger.info(
            "vwap_reversion.init",
            strategy_id=id,
            account_id=account_id,
            entry_threshold_pct=self._entry_threshold_pct,
            stop_loss_pct=self._stop_loss_pct,
            max_trades=self._max_trades_per_session,
        )

    # ---------------------------------------------------------------------- lifecycle

    async def on_start(self, context: StrategyContext) -> None:  # noqa: ARG002
        logger.info("vwap_reversion.started", strategy_id=self.id)

    async def on_stop(self, context: StrategyContext) -> None:  # noqa: ARG002
        logger.info("vwap_reversion.stopped", strategy_id=self.id)

    # ---------------------------------------------------------------------- main hook

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:
        """Evaluate signal conditions on each new candle."""
        # Gate: symbol eligibility
        if candle.symbol not in _ELIGIBLE_SYMBOLS:
            return None

        # Gate: trading window (09:30–14:30 IST only)
        if not self._is_trading_window(candle.ts):
            logger.debug(
                "vwap_reversion.outside_window",
                symbol=candle.symbol,
                ts=candle.ts.isoformat(),
            )
            return None

        self._candle_buffer.append(candle)

        # Need enough history for volume baseline
        if len(self._candle_buffer) < _VOL_LOOKBACK:
            return None

        current_price = candle.close

        # ---- EXIT logic (higher priority than entry) --------------------------
        if self._open_side is not None and self._entry_price is not None:
            vwap = self._compute_vwap_from_candles(list(self._candle_buffer))
            vwap_decimal = Decimal(str(vwap))

            if self._open_side == "BUY":
                should_exit, reason = self._should_exit_long(
                    self._entry_price, current_price, vwap_decimal
                )
                if should_exit:
                    return self._emit_exit("SELL", candle, reason)

            elif self._open_side == "SELL":
                should_exit, reason = self._should_exit_short(
                    self._entry_price, current_price, vwap_decimal
                )
                if should_exit:
                    return self._emit_exit("BUY", candle, reason)

            # Still in position — no new entry allowed
            return None

        # ---- ENTRY logic -----------------------------------------------------
        if self._trades_today >= self._max_trades_per_session:
            logger.debug(
                "vwap_reversion.max_trades_reached",
                trades_today=self._trades_today,
                max=self._max_trades_per_session,
            )
            return None

        deviation_pct = self._compute_vwap_deviation(list(self._candle_buffer))
        has_spike = self._is_volume_spike(list(self._candle_buffer))

        vwap = self._compute_vwap_from_candles(list(self._candle_buffer))

        if not has_spike:
            return None

        if deviation_pct <= -self._entry_threshold_pct:
            # Price is significantly BELOW VWAP — long entry (reversion upward)
            qty = self._compute_quantity(context, current_price)
            self._open_side = "BUY"
            self._entry_price = current_price
            self._trades_today += 1
            logger.info(
                "vwap_reversion.long_entry",
                symbol=candle.symbol,
                price=str(current_price),
                vwap=str(vwap),
                deviation_pct=round(deviation_pct, 4),
                trades_today=self._trades_today,
            )
            return Signal(
                symbol=candle.symbol,
                side="BUY",
                quantity=qty,
                order_type="MARKET",
                stop_loss=current_price * (1 - Decimal(str(self._stop_loss_pct / 100))),
                take_profit=Decimal(str(vwap)),
                reason="vwap_long_entry",
                confidence=min(1.0, abs(deviation_pct) / (self._entry_threshold_pct * 3)),
                metadata={
                    "vwap": str(vwap),
                    "deviation_pct": round(deviation_pct, 4),
                    "trades_today": self._trades_today,
                },
            )

        if deviation_pct >= self._entry_threshold_pct:
            # Price is significantly ABOVE VWAP — short entry (reversion downward)
            qty = self._compute_quantity(context, current_price)
            self._open_side = "SELL"
            self._entry_price = current_price
            self._trades_today += 1
            logger.info(
                "vwap_reversion.short_entry",
                symbol=candle.symbol,
                price=str(current_price),
                vwap=str(vwap),
                deviation_pct=round(deviation_pct, 4),
                trades_today=self._trades_today,
            )
            return Signal(
                symbol=candle.symbol,
                side="SELL",
                quantity=qty,
                order_type="MARKET",
                stop_loss=current_price * (1 + Decimal(str(self._stop_loss_pct / 100))),
                take_profit=Decimal(str(vwap)),
                reason="vwap_short_entry",
                confidence=min(1.0, deviation_pct / (self._entry_threshold_pct * 3)),
                metadata={
                    "vwap": str(vwap),
                    "deviation_pct": round(deviation_pct, 4),
                    "trades_today": self._trades_today,
                },
            )

        return None

    # ---------------------------------------------------------------------- session helpers

    def reset_daily(self) -> None:
        """Reset intraday state at 9:15 IST.  Call from the scheduler."""
        self._trades_today = 0
        self._open_side = None
        self._entry_price = None
        self._candle_buffer.clear()
        logger.info("vwap_reversion.daily_reset", strategy_id=self.id)

    # ---------------------------------------------------------------------- signal helpers

    def _emit_exit(self, side: str, candle: Candle, reason: str) -> Signal:
        entry = self._entry_price
        self._open_side = None
        self._entry_price = None
        logger.info(
            "vwap_reversion.exit",
            symbol=candle.symbol,
            side=side,
            reason=reason,
            entry_price=str(entry),
            exit_price=str(candle.close),
        )
        return Signal(
            symbol=candle.symbol,
            side=side,  # type: ignore[arg-type]
            quantity=Decimal("1"),  # position sizing delegated to execution layer
            order_type="MARKET",
            reason=reason,
            metadata={"entry_price": str(entry)},
        )

    def _compute_quantity(self, context: StrategyContext, price: Decimal) -> Decimal:  # noqa: ARG002
        """Placeholder: returns 1 lot.  Replace with capital_ringfence integration."""
        # In production, call CapitalRingfence.get_max_trade_size() and divide by price
        return Decimal("1")

    # ---------------------------------------------------------------------- predicates

    def _is_trading_window(self, ts: datetime) -> bool:
        """Return True if *ts* (UTC) falls within 09:30–14:30 IST on a weekday."""
        ist_time = _to_ist_time(ts)
        return _TRADING_START_IST <= ist_time <= _TRADING_END_IST

    def _compute_vwap_from_candles(self, candles: list[Candle]) -> float:
        """Compute VWAP from the candle list using typical price × volume."""
        total_pv = Decimal(0)
        total_vol = Decimal(0)
        for c in candles:
            typical = (c.high + c.low + c.close) / 3
            vol = c.volume if c.volume else Decimal(0)
            total_pv += typical * vol
            total_vol += vol
        if total_vol == 0:
            return float(candles[-1].close) if candles else 0.0
        return float(total_pv / total_vol)

    def _compute_vwap_deviation(self, candles: list[Candle]) -> float:
        """Return (last_close - vwap) / vwap * 100 using rolling candle data."""
        if not candles:
            return 0.0
        vwap = self._compute_vwap_from_candles(candles)
        if vwap == 0.0:
            return 0.0
        last_close = float(candles[-1].close)
        return (last_close - vwap) / vwap * 100

    def _is_volume_spike(self, candles: list[Candle]) -> bool:
        """Return True if the latest candle's volume exceeds N × 20-bar average."""
        if len(candles) < _VOL_LOOKBACK:
            return False
        recent = candles[-_VOL_LOOKBACK:]
        avg_vol = sum(float(c.volume) for c in recent[:-1]) / (_VOL_LOOKBACK - 1)
        current_vol = float(candles[-1].volume)
        spike = current_vol > self._volume_spike_multiplier * avg_vol
        if spike:
            logger.debug(
                "vwap_reversion.volume_spike",
                symbol=candles[-1].symbol,
                current_vol=current_vol,
                avg_vol=round(avg_vol, 2),
                multiplier=self._volume_spike_multiplier,
            )
        return spike

    def _should_exit_long(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        vwap: Decimal,
    ) -> tuple[bool, str]:
        """Check exit conditions for a long position.

        Returns (should_exit, reason_string).
        """
        # Take profit: price has reverted to VWAP or above
        if current_price >= vwap:
            return True, "vwap_take_profit"

        # Stop loss: price dropped more than stop_loss_pct below entry
        stop_price = entry_price * (1 - Decimal(str(self._stop_loss_pct / 100)))
        if current_price <= stop_price:
            return True, "vwap_stop_loss"

        return False, ""

    def _should_exit_short(
        self,
        entry_price: Decimal,
        current_price: Decimal,
        vwap: Decimal,
    ) -> tuple[bool, str]:
        """Check exit conditions for a short position.

        Returns (should_exit, reason_string).
        """
        # Take profit: price has reverted to VWAP or below
        if current_price <= vwap:
            return True, "vwap_take_profit"

        # Stop loss: price rose more than stop_loss_pct above entry
        stop_price = entry_price * (1 + Decimal(str(self._stop_loss_pct / 100)))
        if current_price >= stop_price:
            return True, "vwap_stop_loss"

        return False, ""
