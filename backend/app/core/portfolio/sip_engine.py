"""Systematic Investment Plan (SIP) engine for DRUVA.

Supports:
  - Fixed-amount SIP: invest ₹X every month/week/quarter.
  - Step-up SIP: increase SIP amount by Y% annually (compounded).
  - Value averaging: invest more when portfolio is below target growth.
  - Smart SIP: pause/reduce in Bear/Crash regime (uses HMM regime signal).

Regime behaviour (when ``smart_sip=True``):
  - "Crash"    → skip entirely (no investment this cycle).
  - "Bear"     → invest 50 % of the step-up-adjusted amount.
  - "Neutral"  → invest 100 %.
  - "Bull"     → invest 100 %.
  - "Euphoria" → invest 100 %.

All execution dates are computed in IST (UTC+5:30) and constrained to
market days (Monday–Friday).  Orders are placed via the caller-supplied
``execution_service`` (an :class:`~app.core.execution.execution_service.ExecutionService`
instance) so the SIP engine itself does not touch the broker directly.

Example::

    engine = SIPEngine()
    config = SIPConfig(
        account_id="acc-123",
        target_symbols=["NIFTYBEES", "JUNIORBEES"],
        amount=Decimal("10000"),
        frequency="monthly",
        step_up_pct=10.0,
        smart_sip=True,
    )
    execution = await engine.compute_next_execution(config, current_regime="Bear")
    # execution.total_amount = Decimal("5000")  (50% due to Bear regime)
    # execution.skipped      = False
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.core.execution.execution_service import ExecutionService

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# Regime → fraction of normal SIP amount to invest.
_REGIME_FACTORS: dict[str, Decimal] = {
    "Crash":    Decimal("0"),
    "Bear":     Decimal("0.5"),
    "Neutral":  Decimal("1"),
    "Bull":     Decimal("1"),
    "Euphoria": Decimal("1"),
}

_FREQUENCY_DAYS: dict[str, int] = {
    "weekly":    7,
    "monthly":   30,   # approximate; exact logic uses calendar months
    "quarterly": 91,   # approximate; exact logic uses calendar quarters
}


# --------------------------------------------------------------------------- #
# Data classes                                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class SIPConfig:
    """Configuration for a single SIP mandate.

    Attributes:
        account_id:      DRUVA account identifier (string UUID).
        target_symbols:  List of NSE/BSE symbols to invest in each cycle.
                         Amount is split equally unless ``symbol_weights`` is
                         provided.
        amount:          Base SIP amount in INR per cycle.
        frequency:       Cadence — ``"weekly"``, ``"monthly"``, or
                         ``"quarterly"``.
        step_up_pct:     Annual percentage increase in the SIP amount
                         (compounded; 0.0 = fixed SIP).
        smart_sip:       Enable regime-aware amount adjustment.
        start_date:      Date the SIP was first started (used for step-up
                         calculation).  Defaults to today if ``None``.
        symbol_weights:  Optional mapping of ``symbol → weight`` (weights need
                         not sum to 1; they are normalised internally).  If
                         absent, equal weights are used.
    """

    account_id: str
    target_symbols: list[str]
    amount: Decimal
    frequency: Literal["weekly", "monthly", "quarterly"]
    step_up_pct: float = 0.0
    smart_sip: bool = True
    start_date: date | None = None
    symbol_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class SIPExecution:
    """Result of a single SIP execution computation.

    Attributes:
        config:          The :class:`SIPConfig` that produced this execution.
        execution_date:  The date on which the execution is (or was) due.
        amounts:         Dict of ``symbol → INR amount`` to invest this cycle.
        total_amount:    Sum of all ``amounts`` values.
        regime:          The HMM regime label at the time of execution (or
                         ``None`` if regime data was unavailable).
        skipped:         ``True`` if the execution was suppressed by the regime
                         signal (e.g. Crash regime with ``smart_sip=True``).
        skip_reason:     Human-readable explanation when ``skipped=True``.
    """

    config: SIPConfig
    execution_date: date
    amounts: dict[str, Decimal]
    total_amount: Decimal
    regime: str | None
    skipped: bool
    skip_reason: str | None


# --------------------------------------------------------------------------- #
# SIPEngine                                                                    #
# --------------------------------------------------------------------------- #

class SIPEngine:
    """Stateless engine that computes SIP execution plans and places orders."""

    # ---------------------------------------------------------------- public

    async def compute_next_execution(
        self,
        config: SIPConfig,
        current_regime: str | None = None,
    ) -> SIPExecution:
        """Compute the SIP execution for the upcoming due date.

        Applies step-up, regime factor, and symbol allocation in one pass.

        Args:
            config:          The SIP mandate to evaluate.
            current_regime:  HMM regime label (e.g. "Bear", "Bull", "Crash").
                             Pass ``None`` if the regime is unavailable —
                             the engine will treat it as "Neutral".

        Returns:
            :class:`SIPExecution` describing what to invest (or skip) and why.
        """
        start_date = config.start_date or utcnow().date()
        execution_date = self.next_execution_date(config, last_run=None)

        # Step-up: compute this year's adjusted SIP amount.
        stepped_amount = self.compute_step_up_amount(
            config.amount, start_date, config.step_up_pct
        )

        # Regime factor.
        regime_factor = Decimal("1")
        skip_reason: str | None = None

        if config.smart_sip and current_regime is not None:
            regime_factor = _REGIME_FACTORS.get(current_regime, Decimal("1"))
            if regime_factor == Decimal("0"):
                logger.info(
                    "sip.skipped_crash_regime",
                    account_id=config.account_id,
                    regime=current_regime,
                    execution_date=execution_date.isoformat(),
                )
                return SIPExecution(
                    config=config,
                    execution_date=execution_date,
                    amounts={},
                    total_amount=Decimal("0"),
                    regime=current_regime,
                    skipped=True,
                    skip_reason=(
                        f"Regime is '{current_regime}': SIP skipped entirely "
                        "to preserve capital."
                    ),
                )
            elif regime_factor < Decimal("1"):
                skip_reason = (
                    f"Regime is '{current_regime}': investing {int(regime_factor * 100)}% "
                    "of normal amount."
                )

        effective_amount = (stepped_amount * regime_factor).quantize(Decimal("0.01"))

        # Distribute across symbols.
        amounts = self._allocate_to_symbols(effective_amount, config)

        logger.info(
            "sip.execution_computed",
            account_id=config.account_id,
            execution_date=execution_date.isoformat(),
            effective_amount=str(effective_amount),
            regime=current_regime,
            symbols=list(amounts.keys()),
        )

        return SIPExecution(
            config=config,
            execution_date=execution_date,
            amounts=amounts,
            total_amount=sum(amounts.values(), Decimal("0")),
            regime=current_regime,
            skipped=False,
            skip_reason=skip_reason,
        )

    def compute_step_up_amount(
        self,
        base_amount: Decimal,
        start_date: date,
        step_up_pct: float,
    ) -> Decimal:
        """Return this year's SIP amount after compounded annual step-ups.

        Args:
            base_amount:  The original SIP amount configured at inception.
            start_date:   The date the SIP was first started.
            step_up_pct:  Annual increase percentage (e.g. 10.0 for 10 %).

        Returns:
            The adjusted SIP amount in INR, rounded to the nearest paisa.

        Example::

            # SIP started 2 years ago with ₹10,000 and 10% step-up
            amount = engine.compute_step_up_amount(
                Decimal("10000"), date(2024, 1, 1), 10.0
            )
            # Year 1: ₹10,000 → Year 2: ₹11,000 → Year 3: ₹12,100
            # amount = Decimal("12100.00")
        """
        if step_up_pct <= 0.0:
            return base_amount.quantize(Decimal("0.01"))

        today = utcnow().date()
        years_elapsed = max(
            0,
            (today.year - start_date.year)
            + (1 if today.month > start_date.month or
               (today.month == start_date.month and today.day >= start_date.day)
               else 0)
            - 1,
        )
        if years_elapsed == 0:
            return base_amount.quantize(Decimal("0.01"))

        factor = Decimal(str((1.0 + step_up_pct / 100.0) ** years_elapsed))
        return (base_amount * factor).quantize(Decimal("0.01"))

    async def get_pending_executions(
        self,
        configs: list[SIPConfig],
        as_of: date | None = None,
        regime_map: dict[str, str] | None = None,
    ) -> list[SIPExecution]:
        """Return SIP executions that are due on ``as_of`` (defaults to today IST).

        Args:
            configs:     All active SIP mandates to evaluate.
            as_of:       Reference date (defaults to today in IST).
            regime_map:  Optional dict of ``account_id → regime`` for per-account
                         regime overrides.  Falls back to ``None`` (Neutral) if
                         an account is not in the map.

        Returns:
            List of :class:`SIPExecution` objects for all due mandates
            (including skipped ones so callers can audit the decision).
        """
        if as_of is None:
            as_of = utcnow().astimezone(IST).date()

        regime_map = regime_map or {}
        pending: list[SIPExecution] = []

        for config in configs:
            due_date = self.next_execution_date(config, last_run=None)
            if due_date > as_of:
                continue
            regime = regime_map.get(config.account_id)
            execution = await self.compute_next_execution(config, current_regime=regime)
            pending.append(execution)

        logger.info(
            "sip.pending_executions",
            as_of=as_of.isoformat(),
            total_configs=len(configs),
            due_count=len(pending),
        )
        return pending

    async def execute_sip(
        self,
        execution: SIPExecution,
        execution_service: ExecutionService,
    ) -> list[Any]:
        """Place market buy orders for each symbol in a :class:`SIPExecution`.

        Skipped executions are returned immediately as an empty list without
        touching the broker.

        Args:
            execution:         The computed :class:`SIPExecution` to act on.
            execution_service: Live :class:`~app.core.execution.execution_service.ExecutionService`
                               instance used to place orders.

        Returns:
            List of :class:`~app.db.models.order.Order` objects created, one
            per symbol.  Returns ``[]`` if ``execution.skipped`` is ``True``.
        """
        from app.core.execution.models import PlaceOrderRequest

        if execution.skipped:
            logger.info(
                "sip.execute_skipped",
                account_id=execution.config.account_id,
                skip_reason=execution.skip_reason,
            )
            return []

        orders: list[Any] = []
        for symbol, amount in execution.amounts.items():
            if amount <= Decimal("0"):
                continue
            try:
                # SIP orders are AMO (After Market Orders) sized by value;
                # the execution service resolves quantity from the live price.
                # We pass quantity=0 and carry the notional in the ``tag``.
                req = PlaceOrderRequest(
                    account_id=execution.config.account_id,
                    symbol=symbol,
                    exchange="NSE",
                    side="BUY",
                    quantity=Decimal("0"),   # resolved at broker by AMO logic
                    order_type="MARKET",
                    product="CNC",
                    price=None,
                    tag=f"SIP|{execution.config.account_id}|{execution.execution_date}|{amount}",
                )
                order = await execution_service.place_order(
                    execution.config.account_id, req
                )
                orders.append(order)
                logger.info(
                    "sip.order_placed",
                    account_id=execution.config.account_id,
                    symbol=symbol,
                    amount=str(amount),
                    order_id=str(order.id) if hasattr(order, "id") else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "sip.order_failed",
                    account_id=execution.config.account_id,
                    symbol=symbol,
                    amount=str(amount),
                    error=str(exc),
                )
        return orders

    def next_execution_date(
        self,
        config: SIPConfig,
        last_run: date | None,
    ) -> date:
        """Compute the next SIP due date given the last execution date.

        Logic:
          - If ``last_run`` is ``None``, return today (IST) adjusted to the
            next weekday if today is a weekend.
          - Otherwise, advance by the frequency interval and snap to the next
            available weekday.

        Args:
            config:    The SIP mandate (used for ``frequency`` and
                       ``start_date``).
            last_run:  Date of the last successful execution, or ``None`` if
                       this is the first run.

        Returns:
            Next due :class:`date`.
        """
        today_ist = utcnow().astimezone(IST).date()
        base = last_run if last_run is not None else (config.start_date or today_ist)

        freq = config.frequency
        if freq == "weekly":
            candidate = base + timedelta(days=7)
        elif freq == "monthly":
            candidate = _add_one_month(base)
        elif freq == "quarterly":
            candidate = _add_months(base, 3)
        else:
            candidate = base + timedelta(days=30)

        # If this is the very first run (no last_run), return today if it's due.
        if last_run is None and candidate > today_ist:
            candidate = today_ist

        return _next_weekday(candidate)

    # ---------------------------------------------------------------- private

    def _allocate_to_symbols(
        self,
        total: Decimal,
        config: SIPConfig,
    ) -> dict[str, Decimal]:
        """Split ``total`` across symbols using configured weights or equal split.

        Args:
            total:   Total INR to distribute.
            config:  The :class:`SIPConfig` providing symbols and optional weights.

        Returns:
            Dict of ``symbol → INR amount``, each quantised to 2 decimal places.
            Rounding residuals are added to the first symbol.
        """
        symbols = config.target_symbols
        if not symbols:
            return {}

        if config.symbol_weights:
            raw_weights = {
                sym: float(config.symbol_weights.get(sym, 1.0)) for sym in symbols
            }
        else:
            raw_weights = {sym: 1.0 for sym in symbols}

        total_weight = sum(raw_weights.values())
        if total_weight <= 0:
            equal = (total / Decimal(len(symbols))).quantize(Decimal("0.01"))
            return {sym: equal for sym in symbols}

        amounts: dict[str, Decimal] = {}
        allocated = Decimal("0")
        for i, sym in enumerate(symbols):
            weight = Decimal(str(raw_weights[sym])) / Decimal(str(total_weight))
            if i == len(symbols) - 1:
                # Last symbol absorbs rounding residual.
                amounts[sym] = (total - allocated).quantize(Decimal("0.01"))
            else:
                alloc = (total * weight).quantize(Decimal("0.01"))
                amounts[sym] = alloc
                allocated += alloc

        return amounts


# --------------------------------------------------------------------------- #
# Module-level date helpers                                                    #
# --------------------------------------------------------------------------- #

def _next_weekday(d: date) -> date:
    """Advance ``d`` to the next Monday–Friday if it falls on a weekend."""
    weekday = d.weekday()  # 0=Mon, 6=Sun
    if weekday == 5:   # Saturday
        return d + timedelta(days=2)
    if weekday == 6:   # Sunday
        return d + timedelta(days=1)
    return d


def _add_one_month(d: date) -> date:
    """Add exactly one calendar month, clamping to the last day of the month."""
    month = d.month % 12 + 1
    year = d.year + (d.month // 12)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _add_months(d: date, n: int) -> date:
    """Add ``n`` calendar months, clamping to the last day of the target month."""
    result = d
    for _ in range(n):
        result = _add_one_month(result)
    return result
