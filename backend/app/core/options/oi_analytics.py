"""Open-interest analytics built on top of an OptionChain.

- ``oi_profile``: total OI per strike (CE + PE).
- ``oi_change_profile``: OI delta vs. a snapshot taken N minutes ago
  (caller passes the snapshot).
- ``gex_profile``: gamma exposure per strike (sum of dealer-side gamma in
  notional Rs per 1 % spot move).
- ``put_call_ratio``: PCR by OI and by volume.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.options.option_chain import OptionChain


@dataclass(frozen=True)
class OiProfileEntry:
    strike: Decimal
    call_oi: int
    put_oi: int
    call_volume: int
    put_volume: int
    gex: float


@dataclass(frozen=True)
class OiSummary:
    pcr_oi: float
    pcr_volume: float
    max_call_oi_strike: Decimal | None
    max_put_oi_strike: Decimal | None
    total_gex: float


def oi_profile(chain: OptionChain) -> list[OiProfileEntry]:
    out: list[OiProfileEntry] = []
    for row in chain.rows:
        call_oi = row.call.open_interest if row.call else 0
        put_oi = row.put.open_interest if row.put else 0
        call_vol = row.call.volume if row.call else 0
        put_vol = row.put.volume if row.put else 0
        # Standard dealer-hedge convention: dealers are short calls / short
        # puts, so dealer gamma exposure = -(call_oi * call_gamma * S^2 * 0.01)
        # + (put_oi * put_gamma * S^2 * 0.01). We expose total per strike;
        # downstream code can break it out by side.
        spot = float(chain.spot)
        cg = row.call.greeks.gamma if row.call else 0.0
        pg = row.put.greeks.gamma if row.put else 0.0
        gex = (-call_oi * cg + put_oi * pg) * spot * spot * 0.01
        out.append(
            OiProfileEntry(
                strike=row.strike,
                call_oi=call_oi,
                put_oi=put_oi,
                call_volume=call_vol,
                put_volume=put_vol,
                gex=gex,
            )
        )
    return out


def oi_change(prev: list[OiProfileEntry], curr: list[OiProfileEntry]) -> list[OiProfileEntry]:
    """Per-strike delta of (curr - prev) in OI fields. Useful for "OI tracker"
    views that show short build-up / long unwinding."""
    prev_by_strike = {entry.strike: entry for entry in prev}
    out: list[OiProfileEntry] = []
    for c in curr:
        p = prev_by_strike.get(c.strike)
        if p is None:
            out.append(c)
            continue
        out.append(
            OiProfileEntry(
                strike=c.strike,
                call_oi=c.call_oi - p.call_oi,
                put_oi=c.put_oi - p.put_oi,
                call_volume=c.call_volume - p.call_volume,
                put_volume=c.put_volume - p.put_volume,
                gex=c.gex - p.gex,
            )
        )
    return out


def summarise(chain: OptionChain) -> OiSummary:
    profile = oi_profile(chain)
    if not profile:
        return OiSummary(
            pcr_oi=0.0,
            pcr_volume=0.0,
            max_call_oi_strike=None,
            max_put_oi_strike=None,
            total_gex=0.0,
        )
    total_call_oi = sum(p.call_oi for p in profile)
    total_put_oi = sum(p.put_oi for p in profile)
    total_call_vol = sum(p.call_volume for p in profile)
    total_put_vol = sum(p.put_volume for p in profile)
    return OiSummary(
        pcr_oi=(total_put_oi / total_call_oi) if total_call_oi else 0.0,
        pcr_volume=(total_put_vol / total_call_vol) if total_call_vol else 0.0,
        max_call_oi_strike=max(profile, key=lambda p: p.call_oi).strike,
        max_put_oi_strike=max(profile, key=lambda p: p.put_oi).strike,
        total_gex=sum(p.gex for p in profile),
    )
