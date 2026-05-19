"""Iron Condor options strategy for DRUVA.

An Iron Condor profits from low volatility (time decay).
Structure:
  Sell OTM Call (SC) + Buy further OTM Call (LC) — Bear Call Spread
  Sell OTM Put  (SP) + Buy further OTM Put  (LP) — Bull Put Spread

Entry criteria (ALL must be met):
  1. Regime = Neutral (from HMM regime trader)
  2. IV Rank > 40 (selling premium when IV is relatively high)
  3. PCR between 0.7 and 1.3 (neither extreme)
  4. Days to expiry: 7-21 days (weekly NIFTY options)
  5. India VIX < 22 (not extreme fear)

Exit criteria (ANY triggers exit):
  1. Profit = 50% of max profit (take profit early)
  2. Loss = 2x credit received (stop loss)
  3. Days to expiry ≤ 2 (avoid gamma risk)
  4. Regime changes to Bear or Crash

Strikes:
  - SC: 1 std dev OTM call (delta ≈ 0.16)
  - LC: 2 std dev OTM call (further OTM)
  - SP: 1 std dev OTM put (delta ≈ -0.16)
  - LP: 2 std dev OTM put (further OTM)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.options.black_scholes import delta as bs_delta
from app.infrastructure.logging import get_logger
from app.strategies.base import Candle, Signal, Strategy, StrategyContext
from app.strategies.registry import register_strategy

logger = get_logger(__name__)

# Risk-free rate and dividend yield (must match chain_feed.py constants)
_RISK_FREE_RATE: float = 0.065
_DIVIDEND_YIELD: float = 0.015

# Strike rounding for NIFTY (50-point increments)
_NIFTY_STRIKE_GAP: float = 50.0

# ─── Entry thresholds ───────────────────────────────────────────────────────
_MIN_IV_RANK: float = 40.0          # only sell premium above this
_MIN_PCR: float = 0.7               # PCR lower bound
_MAX_PCR: float = 1.3               # PCR upper bound
_MIN_DTE: int = 7                   # minimum days to expiry
_MAX_DTE: int = 21                  # maximum days to expiry
_MAX_VIX: float = 22.0              # don't enter if VIX is above this

# ─── Exit thresholds ────────────────────────────────────────────────────────
_TAKE_PROFIT_FRACTION: float = 0.50  # exit at 50% of max profit
_STOP_LOSS_MULTIPLIER: float = 2.0   # exit at 2× credit received
_MIN_DTE_EXIT: int = 2               # exit if DTE falls to or below this

# ─── Regimes ────────────────────────────────────────────────────────────────
_VALID_ENTRY_REGIMES: set[str] = {"neutral", "sideways", "low_volatility"}
_EXIT_REGIMES: set[str] = {"bear", "crash", "high_volatility"}


@dataclass
class IronCondorLegs:
    """Strike and financial summary of an iron condor position."""

    sell_call_strike: float          # SC — sold OTM call
    buy_call_strike: float           # LC — bought further OTM call
    sell_put_strike: float           # SP — sold OTM put
    buy_put_strike: float            # LP — bought further OTM put
    expiry: date
    net_credit: Decimal              # total premium received (positive)
    max_profit: Decimal              # = net_credit
    max_loss: Decimal                # = wing_width - net_credit (positive)
    breakeven_upper: float           # SC_strike + net_credit
    breakeven_lower: float           # SP_strike - net_credit


@dataclass
class IronCondorState:
    """Runtime state of the iron condor position."""

    legs: IronCondorLegs | None
    is_open: bool
    entry_credit: Decimal            # credit received at entry
    current_value: Decimal           # current mark-to-market value of sold options
    unrealised_pnl: Decimal          # entry_credit - current_value
    days_to_expiry: int


@dataclass
class _EntryContext:
    """Transient data assembled in on_candle, passed to _check_entry."""

    spot: float
    iv: float
    iv_rank: float
    pcr: float
    regime: str
    dte: int
    vix: float


@register_strategy("options.iron_condor.v1")
class IronCondorStrategy(Strategy):
    """Sell an iron condor on NIFTY when conditions favour range-bound moves.

    Parameters (all optional, pulled from ``self.parameters``):
      - ``strike_gap`` (float, default 50.0): NIFTY strike spacing in points
      - ``lot_size``   (int,   default 50):   NIFTY lot size in units
      - ``wing_width_stdev`` (float, default 1.0): outer wing extra std devs beyond inner
    """

    def __init__(
        self, *, id: str, account_id: str, parameters: dict[str, Any] | None = None
    ) -> None:
        super().__init__(id=id, account_id=account_id, parameters=parameters)
        self._state: IronCondorState | None = None
        self._strike_gap: float = float(self.parameters.get("strike_gap", _NIFTY_STRIKE_GAP))
        self._lot_size: int = int(self.parameters.get("lot_size", 50))
        self._wing_extra: float = float(self.parameters.get("wing_width_stdev", 1.0))

    # ──────────────────────────────────────────────── lifecycle

    async def on_start(self, context: StrategyContext) -> None:
        logger.info("iron_condor.on_start", strategy_id=self.id)

    async def on_stop(self, context: StrategyContext) -> None:
        logger.info("iron_condor.on_stop", strategy_id=self.id)
        if self._state and self._state.is_open:
            logger.warning(
                "iron_condor.on_stop: position still open at strategy shutdown",
                strategy_id=self.id,
            )

    # ──────────────────────────────────────────────── main event loop

    async def on_candle(self, candle: Candle, context: StrategyContext) -> Signal | None:
        """Evaluate entry / exit on each new candle.

        The candle metadata dict is expected to carry:
          ``iv``       – current ATM implied volatility (decimal, e.g. 0.18)
          ``iv_rank``  – IV Rank 0-100
          ``pcr``      – Put-Call Ratio
          ``regime``   – string from the regime module
          ``dte``      – integer days-to-expiry for the target options expiry
          ``vix``      – India VIX index level
          ``option_value`` – current mark value of the sold legs (for P&L)
        """
        meta: dict[str, Any] = candle.metadata if hasattr(candle, "metadata") else {}
        spot = float(candle.close)
        iv: float = float(meta.get("iv", 0.18))
        iv_rank: float = float(meta.get("iv_rank", 0.0))
        pcr: float = float(meta.get("pcr", 1.0))
        regime: str = str(meta.get("regime", "neutral")).lower()
        dte: int = int(meta.get("dte", 14))
        vix: float = float(meta.get("vix", 15.0))
        option_value: Decimal = Decimal(str(meta.get("option_value", "0")))

        # ── Manage open position ─────────────────────────────────────
        if self._state and self._state.is_open and self._state.legs:
            # Refresh P&L state
            unrealised_pnl = self._state.entry_credit - option_value
            self._state = IronCondorState(
                legs=self._state.legs,
                is_open=True,
                entry_credit=self._state.entry_credit,
                current_value=option_value,
                unrealised_pnl=unrealised_pnl,
                days_to_expiry=dte,
            )

            should_exit, reason = await self._check_exit(self._state, regime)
            if should_exit:
                logger.info(
                    "iron_condor.on_candle: exit triggered",
                    reason=reason,
                    pnl=str(unrealised_pnl),
                    strategy_id=self.id,
                )
                self._state = IronCondorState(
                    legs=None,
                    is_open=False,
                    entry_credit=Decimal("0"),
                    current_value=Decimal("0"),
                    unrealised_pnl=Decimal("0"),
                    days_to_expiry=0,
                )
                # Signal to close / unwind the condor
                return Signal(
                    symbol=candle.symbol,
                    side="BUY",  # buying back sold legs
                    quantity=Decimal(str(self._lot_size)),
                    order_type="MARKET",
                    reason=f"iron_condor_exit:{reason}",
                    confidence=1.0,
                    metadata={"strategy": "iron_condor", "action": "exit", "exit_reason": reason},
                )
            return None  # hold position

        # ── Evaluate entry ────────────────────────────────────────────
        entry_ok = await self._check_entry(spot, iv, iv_rank, pcr, regime, dte, vix)
        if not entry_ok:
            return None

        sc, lc, sp, lp = self._compute_strikes(spot, iv, dte)
        sc_r = self._round_to_strike(sc, self._strike_gap)
        lc_r = self._round_to_strike(lc, self._strike_gap)
        sp_r = self._round_to_strike(sp, self._strike_gap)
        lp_r = self._round_to_strike(lp, self._strike_gap)

        # Sanity: ensure wings are properly ordered after rounding
        if lc_r <= sc_r:
            lc_r = sc_r + self._strike_gap
        if sp_r <= lp_r:
            lp_r = sp_r - self._strike_gap

        # Estimate credit from mid-prices (caller should override via metadata)
        # Rough placeholder: use Black-Scholes price for now
        T = dte / 365.0
        sc_price = _bs_price(spot, sc_r, T, "CE")
        lc_price = _bs_price(spot, lc_r, T, "CE")
        sp_price = _bs_price(spot, sp_r, T, "PE")
        lp_price = _bs_price(spot, lp_r, T, "PE")

        net_credit_float = (sc_price - lc_price) + (sp_price - lp_price)
        net_credit = Decimal(str(round(net_credit_float, 2)))
        wing_width = Decimal(str(lc_r - sc_r))  # assume equal-width wings
        max_loss = max(Decimal("0"), wing_width - net_credit)

        legs = IronCondorLegs(
            sell_call_strike=sc_r,
            buy_call_strike=lc_r,
            sell_put_strike=sp_r,
            buy_put_strike=lp_r,
            expiry=date.today() + __import__("datetime").timedelta(days=dte),
            net_credit=net_credit,
            max_profit=net_credit,
            max_loss=max_loss,
            breakeven_upper=sc_r + float(net_credit),
            breakeven_lower=sp_r - float(net_credit),
        )

        self._state = IronCondorState(
            legs=legs,
            is_open=True,
            entry_credit=net_credit,
            current_value=net_credit,   # just entered, value = credit received
            unrealised_pnl=Decimal("0"),
            days_to_expiry=dte,
        )

        logger.info(
            "iron_condor.on_candle: entry signal",
            sc=sc_r, lc=lc_r, sp=sp_r, lp=lp_r,
            credit=str(net_credit), max_loss=str(max_loss),
            regime=regime, iv_rank=iv_rank, pcr=pcr,
            strategy_id=self.id,
        )

        return Signal(
            symbol=candle.symbol,
            side="SELL",
            quantity=Decimal(str(self._lot_size)),
            order_type="MARKET",
            reason="iron_condor_entry",
            confidence=0.9,
            metadata={
                "strategy": "iron_condor",
                "action": "entry",
                "sell_call": sc_r,
                "buy_call": lc_r,
                "sell_put": sp_r,
                "buy_put": lp_r,
                "net_credit": str(net_credit),
                "max_loss": str(max_loss),
                "dte": dte,
                "regime": regime,
                "iv_rank": iv_rank,
                "pcr": pcr,
            },
        )

    # ──────────────────────────────────────────────── entry / exit helpers

    async def _check_entry(
        self,
        spot: float,
        iv: float,
        iv_rank: float,
        pcr: float,
        regime: str,
        dte: int,
        vix: float,
    ) -> bool:
        """Validate ALL five iron condor entry criteria.

        Returns True only when every condition is satisfied.
        """
        checks = {
            "regime_neutral": regime in _VALID_ENTRY_REGIMES,
            "iv_rank_high_enough": iv_rank >= _MIN_IV_RANK,
            "pcr_in_range": _MIN_PCR <= pcr <= _MAX_PCR,
            "dte_in_range": _MIN_DTE <= dte <= _MAX_DTE,
            "vix_not_extreme": vix < _MAX_VIX,
        }
        passed = all(checks.values())

        if not passed:
            failed = [k for k, v in checks.items() if not v]
            logger.debug(
                "iron_condor._check_entry: criteria not met",
                failed=failed,
                iv_rank=iv_rank,
                pcr=pcr,
                dte=dte,
                vix=vix,
                regime=regime,
            )
        return passed

    def _compute_strikes(
        self, spot: float, iv: float, dte: int
    ) -> tuple[float, float, float, float]:
        """Compute raw (pre-rounding) strike levels using log-normal std dev.

        1 std dev move = spot * exp(±IV * sqrt(DTE/365)) — log-normal displacement.

        Inner wings (SC/SP): ±1 std dev → delta ≈ 0.16
        Outer wings (LC/LP): ±(1 + wing_extra) std devs → delta ≈ 0.05
        """
        T = dte / 365.0
        sigma_sqrt_T = iv * math.sqrt(T)

        # Inner strikes (sell legs)
        sell_call = spot * math.exp(sigma_sqrt_T)
        sell_put = spot * math.exp(-sigma_sqrt_T)

        # Outer strikes (buy legs — hedge)
        outer_sigma = sigma_sqrt_T * (1.0 + self._wing_extra)
        buy_call = spot * math.exp(outer_sigma)
        buy_put = spot * math.exp(-outer_sigma)

        logger.debug(
            "iron_condor._compute_strikes",
            spot=spot, iv=iv, dte=dte,
            sell_call=sell_call, buy_call=buy_call,
            sell_put=sell_put, buy_put=buy_put,
        )
        return sell_call, buy_call, sell_put, buy_put

    async def _check_exit(
        self, state: IronCondorState, current_regime: str
    ) -> tuple[bool, str]:
        """Evaluate ALL exit conditions and return (should_exit, reason).

        Returns the first triggered exit condition.
        """
        if not state.is_open or state.legs is None:
            return False, ""

        # 1. Profit target: 50% of max profit
        if state.max_profit > Decimal("0"):
            profit_pct = state.unrealised_pnl / state.entry_credit
            if profit_pct >= Decimal(str(_TAKE_PROFIT_FRACTION)):
                return True, "take_profit"

        # 2. Stop loss: unrealised loss exceeds 2× credit
        if state.unrealised_pnl < Decimal("0"):
            loss = -state.unrealised_pnl
            if loss >= state.entry_credit * Decimal(str(_STOP_LOSS_MULTIPLIER)):
                return True, "stop_loss"

        # 3. Gamma risk: too close to expiry
        if state.days_to_expiry <= _MIN_DTE_EXIT:
            return True, "near_expiry"

        # 4. Regime change to directional or volatile
        if current_regime in _EXIT_REGIMES:
            return True, f"regime_change:{current_regime}"

        return False, ""

    def _round_to_strike(self, price: float, strike_gap: float = 50.0) -> float:
        """Round ``price`` to the nearest NIFTY strike (50-point grid)."""
        return round(price / strike_gap) * strike_gap

    @property
    def state(self) -> IronCondorState | None:
        """Expose current position state (read-only access for testing/monitoring)."""
        return self._state


# ─── Module-level helper ────────────────────────────────────────────────────

def _bs_price(spot: float, strike: float, T: float, option_type: str) -> float:
    """Convenience wrapper: Black-Scholes price with DRUVA default rates."""
    from app.core.options.black_scholes import price as bs_price_fn

    return bs_price_fn(
        S=spot,
        K=strike,
        T=max(T, 1e-6),
        r=_RISK_FREE_RATE,
        sigma=0.18,   # default 18% vol when not otherwise known
        option_type=option_type,
        q=_DIVIDEND_YIELD,
    )
