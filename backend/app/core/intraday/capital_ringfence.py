"""Capital ring-fence: separates scalping capital from long-term portfolio.

Prevents a bad scalp day from destroying the long-term portfolio.

Architecture:
  Total Portfolio = Long-term Portfolio + Scalping Pool + Cash Reserve

  Scalping Pool: fixed % of total (default 5-10%)
  Long-term Portfolio: never touched by scalping strategies
  Cash Reserve: minimum 10% always available

  Daily loss limit on Scalping Pool: -20% of pool (hard stop for the day)
  If scalping pool drops below minimum threshold: auto-refill from cash
  If scalping pool > 2x initial: lock in profits (move excess to long-term)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")

# Minimum scalping pool size below which trading is halted (absolute floor, % of initial pool)
_MIN_POOL_PCT_OF_INITIAL: Decimal = Decimal("20")  # stop if pool < 20% of its initial size

# Max single trade size as % of pool
_MAX_TRADE_PCT_OF_POOL: Decimal = Decimal("2")


def _to_decimal(value: float | int | str | Decimal) -> Decimal:
    return Decimal(str(value))


@dataclass
class RingfenceConfig:
    """Immutable configuration for the capital ring-fence."""

    total_portfolio_value: Decimal
    scalping_pool_pct: float = 7.0          # % of total allocated to scalping
    cash_reserve_pct: float = 10.0          # % of total kept as cash reserve (minimum)
    daily_loss_limit_pct: float = 20.0      # max daily loss on scalping pool before halt
    profit_lock_multiplier: float = 2.0     # move excess to LTPF when pool > N × initial

    def __post_init__(self) -> None:
        if self.scalping_pool_pct <= 0 or self.scalping_pool_pct >= 100:
            raise ValueError("scalping_pool_pct must be between 0 and 100 exclusive")
        if self.cash_reserve_pct < 0 or self.cash_reserve_pct >= 100:
            raise ValueError("cash_reserve_pct must be between 0 and 100")
        if self.scalping_pool_pct + self.cash_reserve_pct >= 100:
            raise ValueError("scalping_pool_pct + cash_reserve_pct must be < 100")
        if self.daily_loss_limit_pct <= 0 or self.daily_loss_limit_pct > 100:
            raise ValueError("daily_loss_limit_pct must be between 0 and 100")
        if self.profit_lock_multiplier <= 1:
            raise ValueError("profit_lock_multiplier must be > 1")


@dataclass
class RingfenceState:
    """Mutable snapshot of the ring-fence pools."""

    scalping_pool: Decimal
    long_term_portfolio: Decimal
    cash_reserve: Decimal
    daily_scalping_pnl: Decimal = field(default_factory=lambda: Decimal("0"))
    is_scalping_halted: bool = False
    halt_reason: str | None = None

    @property
    def total(self) -> Decimal:
        return self.scalping_pool + self.long_term_portfolio + self.cash_reserve


class CapitalRingfence:
    """Enforces strict capital isolation between scalping and long-term portfolios.

    All monetary amounts are :class:`decimal.Decimal`.

    Typical lifecycle::

        ringfence = CapitalRingfence(config)
        state = ringfence.allocate(total_portfolio_value)

        # after each scalp trade:
        state = ringfence.update_scalping_pnl(trade_pnl)

        # before placing a trade:
        allowed, reason = ringfence.is_scalping_allowed()
        max_size = ringfence.get_max_trade_size()

        # at end of day:
        ringfence.daily_reset()
    """

    def __init__(self, config: RingfenceConfig) -> None:
        self.config = config
        self._state: RingfenceState | None = None
        self._initial_pool: Decimal = _ZERO  # pool size at last allocation/reset

        logger.info(
            "capital_ringfence.init",
            scalping_pool_pct=config.scalping_pool_pct,
            cash_reserve_pct=config.cash_reserve_pct,
            daily_loss_limit_pct=config.daily_loss_limit_pct,
            profit_lock_multiplier=config.profit_lock_multiplier,
        )

    # ---------------------------------------------------------------------- allocation

    def allocate(self, total: Decimal) -> RingfenceState:
        """Perform initial pool allocation from *total* portfolio value.

        Splits capital into:
          - Scalping pool (``scalping_pool_pct``% of total)
          - Cash reserve (``cash_reserve_pct``% of total)
          - Long-term portfolio (remainder)

        Args:
            total: Total portfolio value at the time of allocation.

        Returns:
            The initial :class:`RingfenceState`.
        """
        if total <= _ZERO:
            raise ValueError(f"total must be positive, got {total}")

        scalping_pool = (total * _to_decimal(self.config.scalping_pool_pct) / _HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        cash_reserve = (total * _to_decimal(self.config.cash_reserve_pct) / _HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        long_term = total - scalping_pool - cash_reserve

        if long_term < _ZERO:
            raise ValueError(
                "Allocation error: scalping_pool_pct + cash_reserve_pct >= 100%"
            )

        self._initial_pool = scalping_pool
        self._state = RingfenceState(
            scalping_pool=scalping_pool,
            long_term_portfolio=long_term,
            cash_reserve=cash_reserve,
            daily_scalping_pnl=_ZERO,
            is_scalping_halted=False,
            halt_reason=None,
        )

        logger.info(
            "capital_ringfence.allocated",
            total=str(total),
            scalping_pool=str(scalping_pool),
            long_term_portfolio=str(long_term),
            cash_reserve=str(cash_reserve),
        )
        return self._state

    # ---------------------------------------------------------------------- pnl update

    def update_scalping_pnl(self, pnl: Decimal) -> RingfenceState:
        """Apply *pnl* (positive = profit, negative = loss) to the scalping pool.

        Automatically halts scalping if the daily loss limit is breached or the
        pool falls below the minimum threshold.

        Args:
            pnl: Realised P&L of the completed scalp trade.

        Returns:
            Updated :class:`RingfenceState`.
        """
        state = self._require_state()

        prev_pool = state.scalping_pool
        prev_pnl = state.daily_scalping_pnl

        state.scalping_pool = (state.scalping_pool + pnl).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        state.daily_scalping_pnl = (prev_pnl + pnl).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        logger.info(
            "capital_ringfence.pnl_update",
            pnl=str(pnl),
            scalping_pool_before=str(prev_pool),
            scalping_pool_after=str(state.scalping_pool),
            daily_pnl=str(state.daily_scalping_pnl),
        )

        # Check halt conditions after every P&L update
        allowed, reason = self.is_scalping_allowed()
        if not allowed and not state.is_scalping_halted:
            state.is_scalping_halted = True
            state.halt_reason = reason
            logger.error(
                "capital_ringfence.scalping_HALTED",
                reason=reason,
                scalping_pool=str(state.scalping_pool),
                daily_pnl=str(state.daily_scalping_pnl),
            )

        return state

    # ---------------------------------------------------------------------- guards

    def is_scalping_allowed(self) -> tuple[bool, str]:
        """Check whether scalping may continue.

        Checks:
          1. Daily loss limit: daily_scalping_pnl <= -(daily_loss_limit_pct)% of initial pool
          2. Pool floor: scalping_pool < 20% of initial pool value

        Returns:
            ``(True, "")`` if scalping is allowed, else ``(False, reason_string)``.
        """
        state = self._require_state()

        if state.is_scalping_halted and state.halt_reason:
            return False, state.halt_reason

        # Daily loss limit
        loss_limit = self._initial_pool * _to_decimal(self.config.daily_loss_limit_pct) / _HUNDRED
        if state.daily_scalping_pnl <= -loss_limit:
            reason = (
                f"daily_loss_limit_breached: pnl={state.daily_scalping_pnl}, "
                f"limit=-{loss_limit}"
            )
            return False, reason

        # Pool floor (20% of initial pool)
        pool_floor = self._initial_pool * _MIN_POOL_PCT_OF_INITIAL / _HUNDRED
        if state.scalping_pool <= pool_floor:
            reason = (
                f"pool_below_floor: pool={state.scalping_pool}, "
                f"floor={pool_floor}"
            )
            return False, reason

        return True, ""

    def get_max_trade_size(self) -> Decimal:
        """Return the maximum capital for a single scalp trade.

        Enforces 2% of current scalping pool per trade.
        Returns zero if scalping is halted.
        """
        state = self._require_state()

        allowed, _ = self.is_scalping_allowed()
        if not allowed:
            return _ZERO

        max_size = (
            state.scalping_pool * _MAX_TRADE_PCT_OF_POOL / _HUNDRED
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        logger.debug(
            "capital_ringfence.max_trade_size",
            scalping_pool=str(state.scalping_pool),
            max_trade_size=str(max_size),
        )
        return max_size

    # ---------------------------------------------------------------------- profit locking

    def should_lock_profits(self) -> tuple[bool, Decimal]:
        """Check if the scalping pool has grown enough to lock in profits.

        Profits are locked by moving the *excess* above the initial pool value
        into the long-term portfolio, keeping the pool at exactly ``profit_lock_multiplier``
        times its initial size as the new ceiling.

        Returns:
            ``(True, amount_to_move)`` if profits should be locked, else ``(False, Decimal(0))``.
        """
        state = self._require_state()

        lock_threshold = self._initial_pool * _to_decimal(self.config.profit_lock_multiplier)
        if state.scalping_pool > lock_threshold:
            excess = (state.scalping_pool - lock_threshold).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            logger.info(
                "capital_ringfence.profit_lock_triggered",
                scalping_pool=str(state.scalping_pool),
                lock_threshold=str(lock_threshold),
                excess=str(excess),
            )
            return True, excess
        return False, _ZERO

    # ---------------------------------------------------------------------- rebalancing

    def rebalance_pools(self) -> dict[str, Decimal]:
        """Compute target pool sizes based on current total and configured percentages.

        Call this when significant drift has occurred (e.g. after locking profits
        or after a large long-term portfolio gain).

        Returns:
            Dict with keys ``scalping_pool``, ``long_term_portfolio``, ``cash_reserve``,
            and ``total``.  Does NOT automatically apply the new allocation — the caller
            should transfer funds and then call ``allocate()`` with the new total.
        """
        state = self._require_state()
        total = state.total

        new_scalping = (
            total * _to_decimal(self.config.scalping_pool_pct) / _HUNDRED
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        new_cash = (
            total * _to_decimal(self.config.cash_reserve_pct) / _HUNDRED
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        new_ltpf = total - new_scalping - new_cash

        result = {
            "scalping_pool": new_scalping,
            "long_term_portfolio": new_ltpf,
            "cash_reserve": new_cash,
            "total": total,
        }

        logger.info(
            "capital_ringfence.rebalance_computed",
            **{k: str(v) for k, v in result.items()},
            current_scalping=str(state.scalping_pool),
            current_ltpf=str(state.long_term_portfolio),
        )
        return result

    # ---------------------------------------------------------------------- daily reset

    def daily_reset(self) -> None:
        """Reset daily_scalping_pnl and clear the halt flag at 9:15 IST.

        The scalping pool balance is preserved — only the per-day loss counter
        and halt state are cleared.  Call from the scheduler at market open.
        """
        state = self._require_state()
        prev_pnl = state.daily_scalping_pnl
        prev_halted = state.is_scalping_halted

        state.daily_scalping_pnl = _ZERO
        state.is_scalping_halted = False
        state.halt_reason = None
        # Also update the initial pool reference so daily limits are relative to
        # today's opening pool size (accounts for yesterday's P&L being carried over)
        self._initial_pool = state.scalping_pool

        logger.info(
            "capital_ringfence.daily_reset",
            previous_daily_pnl=str(prev_pnl),
            was_halted=prev_halted,
            new_initial_pool=str(self._initial_pool),
            ts=utcnow().isoformat(),
        )

    # ---------------------------------------------------------------------- helpers

    @property
    def state(self) -> RingfenceState:
        """Current ring-fence state. Raises RuntimeError if allocate() was not called."""
        return self._require_state()

    def _require_state(self) -> RingfenceState:
        if self._state is None:
            raise RuntimeError(
                "CapitalRingfence.allocate() must be called before using this instance."
            )
        return self._state
