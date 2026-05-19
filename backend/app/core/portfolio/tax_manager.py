"""Indian capital gains tax manager for portfolio rebalancing decisions.

Indian tax rules (FY 2025-26):
  Equity (listed):
    STCG (< 12 months): 20% flat (post Budget 2024)
    LTCG (≥ 12 months): 12.5% on gains > ₹1.25 lakh/year (post Budget 2024)

  Equity Mutual Funds:
    Same as equity above.

The tax manager flags positions to AVOID selling (to stay LTCG).
It also estimates the after-tax gain for any proposed sale.

Example::

    mgr = TaxManager()
    profile = mgr.profile_holding(
        symbol="RELIANCE",
        quantity=Decimal("10"),
        buy_date=date(2024, 3, 1),
        buy_price=Decimal("2800"),
        current_price=Decimal("3200"),
    )
    # profile.is_ltcg = False  (held < 12 months as of the example date)
    # profile.unrealised_gain = Decimal("4000")
    # profile.estimated_tax   = Decimal("800")  (20% STCG)
    # profile.after_tax_gain  = Decimal("3200")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

logger = get_logger(__name__)

# --------------------------------------------------------------------------- #
# Constants (FY 2025-26 post Budget 2024)                                     #
# --------------------------------------------------------------------------- #

STCG_RATE: float = 0.20           # 20 % flat on short-term capital gains
LTCG_RATE: float = 0.125          # 12.5 % on long-term capital gains
LTCG_EXEMPTION: Decimal = Decimal("125000")   # ₹1.25 lakh annual exemption
LTCG_HOLDING_DAYS: int = 365      # >= 365 days → qualifies as LTCG

_STCG_RATE_D = Decimal(str(STCG_RATE))
_LTCG_RATE_D = Decimal(str(LTCG_RATE))


# --------------------------------------------------------------------------- #
# Data classes                                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class HoldingTaxProfile:
    """Tax profile for a single holding lot.

    Attributes:
        symbol:           NSE/BSE ticker symbol.
        quantity:         Number of shares/units held.
        buy_date:         Date of purchase (used for holding-period computation).
        buy_price:        Purchase price per share in INR.
        current_price:    Current market price per share in INR.
        holding_days:     Calendar days the position has been held as of today.
        is_ltcg:          True if ``holding_days >= 365`` (qualifies for LTCG).
        unrealised_gain:  Total gross gain in INR (can be negative for a loss).
        estimated_tax:    Estimated tax liability in INR.
        after_tax_gain:   ``unrealised_gain - estimated_tax`` (can be negative).
    """

    symbol: str
    quantity: Decimal
    buy_date: date
    buy_price: Decimal
    current_price: Decimal
    holding_days: int
    is_ltcg: bool
    unrealised_gain: Decimal
    estimated_tax: Decimal
    after_tax_gain: Decimal


# --------------------------------------------------------------------------- #
# TaxManager                                                                   #
# --------------------------------------------------------------------------- #

class TaxManager:
    """Compute tax implications and guide lot-selection for tax efficiency."""

    # ---------------------------------------------------------------- public

    def profile_holding(
        self,
        symbol: str,
        quantity: Decimal,
        buy_date: date,
        buy_price: Decimal,
        current_price: Decimal,
        *,
        as_of: date | None = None,
        ltcg_used_this_year: Decimal = Decimal("0"),
    ) -> HoldingTaxProfile:
        """Build a :class:`HoldingTaxProfile` for a single lot.

        Args:
            symbol:               Ticker symbol.
            quantity:             Number of shares/units held.
            buy_date:             Date the position was opened.
            buy_price:            Entry price per share in INR.
            current_price:        Current market price per share in INR.
            as_of:                Reference date for holding-period computation
                                  (defaults to today UTC).
            ltcg_used_this_year:  LTCG exemption already consumed by earlier
                                  realisations this FY (₹0–₹1.25 lakh).

        Returns:
            :class:`HoldingTaxProfile` with all derived tax fields populated.
        """
        as_of = as_of or utcnow().date()

        if quantity <= Decimal("0"):
            logger.warning("tax.zero_quantity", symbol=symbol, quantity=str(quantity))
            quantity = Decimal("0")

        holding_days = (as_of - buy_date).days
        is_ltcg = holding_days >= LTCG_HOLDING_DAYS

        cost_basis = buy_price * quantity
        market_value = current_price * quantity
        unrealised_gain = market_value - cost_basis

        estimated_tax = self.estimate_tax(
            gain=unrealised_gain,
            holding_days=holding_days,
            ltcg_used_this_year=ltcg_used_this_year,
        )
        after_tax_gain = unrealised_gain - estimated_tax

        logger.debug(
            "tax.profile_holding",
            symbol=symbol,
            holding_days=holding_days,
            is_ltcg=is_ltcg,
            unrealised_gain=str(unrealised_gain),
            estimated_tax=str(estimated_tax),
        )

        return HoldingTaxProfile(
            symbol=symbol,
            quantity=quantity,
            buy_date=buy_date,
            buy_price=buy_price,
            current_price=current_price,
            holding_days=holding_days,
            is_ltcg=is_ltcg,
            unrealised_gain=unrealised_gain,
            estimated_tax=estimated_tax,
            after_tax_gain=after_tax_gain,
        )

    def should_defer_sale(
        self,
        holding: HoldingTaxProfile,
        days_to_ltcg: int = 30,
    ) -> tuple[bool, str]:
        """Recommend whether to defer a sale to reach LTCG treatment.

        The rule is simple: if the holding is currently STCG *and* will cross
        the LTCG threshold within ``days_to_ltcg`` calendar days, it is almost
        always worth waiting to save the 7.5 % tax differential (20 % STCG vs
        12.5 % LTCG).

        Args:
            holding:       A :class:`HoldingTaxProfile` for the lot.
            days_to_ltcg:  How many days before the LTCG anniversary to start
                           recommending deferral (default 30).

        Returns:
            ``(True, reason)`` if the sale should be deferred, else
            ``(False, reason)``.

        Example::

            defer, why = mgr.should_defer_sale(profile, days_to_ltcg=30)
            # defer=True, why="Hold for 18 more days to qualify for LTCG ..."
        """
        if holding.is_ltcg:
            return False, "Position already qualifies for LTCG treatment."

        if holding.unrealised_gain <= Decimal("0"):
            return False, "No unrealised gain — tax deferral is not applicable."

        days_remaining = LTCG_HOLDING_DAYS - holding.holding_days
        if days_remaining <= 0:
            # Should not happen if is_ltcg is computed correctly, but guard anyway.
            return False, "Position has already crossed the LTCG holding threshold."

        if days_remaining <= days_to_ltcg:
            stcg_tax = (holding.unrealised_gain * _STCG_RATE_D).quantize(Decimal("0.01"))
            # Approximate LTCG tax (no exemption offset for simplicity in this
            # per-lot advisory; callers can call estimate_tax for precision).
            ltcg_tax = (holding.unrealised_gain * _LTCG_RATE_D).quantize(Decimal("0.01"))
            saving = (stcg_tax - ltcg_tax).quantize(Decimal("0.01"))
            reason = (
                f"Defer sale by {days_remaining} day(s): holding {holding.symbol} until LTCG "
                f"saves ~₹{saving:,} in tax (STCG ₹{stcg_tax:,} → LTCG ₹{ltcg_tax:,})."
            )
            return True, reason

        return (
            False,
            f"{holding.symbol} needs {days_remaining} more day(s) for LTCG — "
            f"outside the {days_to_ltcg}-day deferral window; sell if required.",
        )

    def estimate_tax(
        self,
        gain: Decimal,
        holding_days: int,
        ltcg_used_this_year: Decimal = Decimal("0"),
    ) -> Decimal:
        """Compute the Indian capital-gains tax on a realised gain.

        Args:
            gain:                 Gross realised gain in INR (negative = loss,
                                  which incurs zero tax).
            holding_days:         Number of calendar days the asset was held.
            ltcg_used_this_year:  LTCG exemption already used this FY (reduces
                                  the remaining ₹1.25 lakh headroom).

        Returns:
            Tax liability in INR, rounded to the nearest paisa (``Decimal``).

        Example::

            # LTCG of ₹2 lakh, no prior exemption used
            tax = mgr.estimate_tax(Decimal("200000"), holding_days=400)
            # ₹(200000 - 125000) * 12.5% = ₹9,375

            # STCG of ₹50,000
            tax = mgr.estimate_tax(Decimal("50000"), holding_days=180)
            # ₹50,000 * 20% = ₹10,000
        """
        if gain <= Decimal("0"):
            # Losses incur no tax (they can be carried forward, but that's out
            # of scope for this estimator).
            return Decimal("0")

        is_ltcg = holding_days >= LTCG_HOLDING_DAYS

        if not is_ltcg:
            # STCG: flat 20 % on the entire gain, no exemption.
            return (gain * _STCG_RATE_D).quantize(Decimal("0.01"))

        # LTCG: 12.5 % on gain *above* the remaining annual exemption.
        remaining_exemption = max(
            Decimal("0"),
            LTCG_EXEMPTION - max(Decimal("0"), ltcg_used_this_year),
        )
        taxable_gain = max(Decimal("0"), gain - remaining_exemption)
        return (taxable_gain * _LTCG_RATE_D).quantize(Decimal("0.01"))

    def tax_aware_sell_order(
        self,
        holdings: list[HoldingTaxProfile],
        target_sell_value: Decimal,
    ) -> list[HoldingTaxProfile]:
        """Select which lots to sell to achieve ``target_sell_value`` with minimal tax.

        Strategy:
          1. Sell LTCG lots first (lower tax rate, exemption available).
          2. Within each tier, prefer lots with larger unrealised gains
             (maximise the amount sold while using the cheapest tax treatment).
          3. Fill with STCG lots only if LTCG lots are exhausted.

        Args:
            holdings:          All available lots (must have ``current_price`` > 0).
            target_sell_value: The total market value to raise in INR.

        Returns:
            Ordered list of :class:`HoldingTaxProfile` lots to sell (partial
            lots are not split — callers should handle partial fills via a
            separate quantity adjustment if needed).

        Example::

            lots_to_sell = mgr.tax_aware_sell_order(all_lots, Decimal("500000"))
        """
        if target_sell_value <= Decimal("0"):
            return []

        # Sort: LTCG lots first, then by descending market value per lot.
        def _sort_key(h: HoldingTaxProfile) -> tuple[int, Decimal]:
            mv = h.current_price * h.quantity
            return (0 if h.is_ltcg else 1, -mv)

        sorted_holdings = sorted(holdings, key=_sort_key)

        selected: list[HoldingTaxProfile] = []
        remaining = target_sell_value

        for lot in sorted_holdings:
            if remaining <= Decimal("0"):
                break
            lot_value = lot.current_price * lot.quantity
            if lot_value <= Decimal("0") or lot.quantity <= Decimal("0"):
                continue
            selected.append(lot)
            remaining -= lot_value

        logger.info(
            "tax.sell_order",
            n_lots_selected=len(selected),
            target_sell_value=str(target_sell_value),
            raised=str(target_sell_value - max(Decimal("0"), remaining)),
        )
        return selected

    def annual_tax_estimate(self, realized_trades: list[dict[str, Any]]) -> dict[str, Any]:
        """Estimate total annual tax liability from a list of realised trades.

        Each trade dict should contain:
          * ``"gain"``         (str | float | Decimal) — realised gain in INR.
          * ``"holding_days"`` (int)                   — days held.

        Args:
            realized_trades: List of realised trade records for the FY.

        Returns:
            Dict with keys:
              * ``stcg_gains``      — total STCG gains (INR).
              * ``ltcg_gains``      — total LTCG gains (INR).
              * ``stcg_tax``        — total STCG tax (INR).
              * ``ltcg_tax``        — total LTCG tax (INR).
              * ``total_tax``       — combined tax liability (INR).
              * ``effective_rate``  — total_tax / total_gains as a float.

        Example::

            result = mgr.annual_tax_estimate([
                {"gain": "150000", "holding_days": 400},  # LTCG
                {"gain": "50000",  "holding_days": 180},  # STCG
            ])
            # result["total_tax"] = Decimal("13125")
            # result["effective_rate"] ≈ 0.065625
        """
        stcg_gains = Decimal("0")
        ltcg_gains = Decimal("0")
        stcg_tax = Decimal("0")
        ltcg_tax_accum = Decimal("0")
        ltcg_used = Decimal("0")   # tracks exemption consumption through the FY

        for trade in realized_trades:
            raw_gain = trade.get("gain", "0")
            try:
                gain = Decimal(str(raw_gain))
            except Exception:  # noqa: BLE001
                logger.warning("tax.bad_gain_value", raw=repr(raw_gain))
                continue

            days = int(trade.get("holding_days", 0))
            is_ltcg = days >= LTCG_HOLDING_DAYS

            if gain <= Decimal("0"):
                # Losses — skip for tax computation (carry-forward out of scope).
                continue

            if is_ltcg:
                ltcg_gains += gain
                tax = self.estimate_tax(gain, days, ltcg_used_this_year=ltcg_used)
                ltcg_tax_accum += tax
                # Consume exemption headroom progressively.
                ltcg_used = min(ltcg_used + gain, LTCG_EXEMPTION)
            else:
                stcg_gains += gain
                tax = self.estimate_tax(gain, days)
                stcg_tax += tax

        total_gains = stcg_gains + ltcg_gains
        total_tax = stcg_tax + ltcg_tax_accum
        effective_rate = float(total_tax / total_gains) if total_gains > 0 else 0.0

        result: dict[str, Any] = {
            "stcg_gains": stcg_gains,
            "ltcg_gains": ltcg_gains,
            "stcg_tax": stcg_tax,
            "ltcg_tax": ltcg_tax_accum,
            "total_tax": total_tax,
            "effective_rate": round(effective_rate, 6),
        }
        logger.info(
            "tax.annual_estimate",
            stcg_tax=str(stcg_tax),
            ltcg_tax=str(ltcg_tax_accum),
            total_tax=str(total_tax),
            effective_rate=round(effective_rate, 6),
        )
        return result
