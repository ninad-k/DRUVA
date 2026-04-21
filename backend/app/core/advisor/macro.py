"""Macro regime detector — mirrors the ROC(18, monthly) heuristic from the
transcript. When the 18-month RoC of Nifty is near 0, we're near a cycle
bottom; near 45, near a top. Same idea on Smallcap-100 with 20/100 bands.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.advisor.indicators import roc
from app.db.models.advisor import MacroRegime


@dataclass(frozen=True)
class MacroReading:
    regime: MacroRegime
    nifty_roc: float | None
    smallcap_roc: float | None
    note: str


def classify(nifty_monthly_closes: list[float], smallcap_monthly_closes: list[float]) -> MacroReading:
    n_roc = roc(nifty_monthly_closes, 18)
    s_roc = roc(smallcap_monthly_closes, 20)

    if n_roc is None and s_roc is None:
        return MacroReading(MacroRegime.NEUTRAL, None, None, "insufficient_history")

    # Use the more extreme of the two signals to decide.
    nifty_hot = n_roc is not None and n_roc >= 35
    nifty_cold = n_roc is not None and n_roc <= 5
    small_hot = s_roc is not None and s_roc >= 80
    small_cold = s_roc is not None and s_roc <= 10

    if nifty_hot or small_hot:
        return MacroReading(MacroRegime.DEFENSIVE, n_roc, s_roc,
                            "cycle_top_zone — reduce exposure, rotate to gold/bonds")
    if nifty_cold or small_cold:
        return MacroReading(MacroRegime.AGGRESSIVE, n_roc, s_roc,
                            "cycle_bottom_zone — deploy capital in equities")
    return MacroReading(MacroRegime.NEUTRAL, n_roc, s_roc, "mid_cycle — normal allocation")


def allocation_multiplier(regime: MacroRegime) -> float:
    """How much of the user's available capital to deploy."""
    return {
        MacroRegime.AGGRESSIVE: 1.0,
        MacroRegime.NEUTRAL: 0.7,
        MacroRegime.DEFENSIVE: 0.35,
    }[regime]
