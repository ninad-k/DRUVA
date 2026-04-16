"""Implied volatility analytics: IV smile, IV chart history, vol surface.

Pure-functional helpers built on top of an OptionChain or list of chains.
Persistence (storing daily IV snapshots for the IV chart) is the caller's
job — these functions are deterministic and side-effect-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.options.option_chain import OptionChain


@dataclass(frozen=True)
class IvSmilePoint:
    strike: Decimal
    call_iv: float
    put_iv: float
    moneyness: float  # K/S


@dataclass(frozen=True)
class IvSurfacePoint:
    expiry: date
    strike: Decimal
    iv: float
    moneyness: float


def iv_smile(chain: OptionChain) -> list[IvSmilePoint]:
    """Return CE + PE IV per strike. With moneyness so the UI can plot vs
    the smile axis without knowing spot."""
    spot = float(chain.spot)
    out: list[IvSmilePoint] = []
    for row in chain.rows:
        call_iv = row.call.iv if row.call else 0.0
        put_iv = row.put.iv if row.put else 0.0
        out.append(
            IvSmilePoint(
                strike=row.strike,
                call_iv=call_iv,
                put_iv=put_iv,
                moneyness=float(row.strike) / spot if spot else 0.0,
            )
        )
    return out


def vol_surface(chains: list[OptionChain]) -> list[IvSurfacePoint]:
    """Stitch a vol surface from chains across multiple expiries.

    The caller passes one chain per expiry sorted by expiry date. We use
    the put IV when available (cleaner OTM calibration on most Indian
    indices), falling back to the call IV otherwise.
    """
    out: list[IvSurfacePoint] = []
    for chain in chains:
        spot = float(chain.spot)
        for row in chain.rows:
            iv = 0.0
            if row.put and row.put.iv > 0:
                iv = row.put.iv
            elif row.call and row.call.iv > 0:
                iv = row.call.iv
            out.append(
                IvSurfacePoint(
                    expiry=chain.expiry,
                    strike=row.strike,
                    iv=iv,
                    moneyness=float(row.strike) / spot if spot else 0.0,
                )
            )
    return out


def atm_iv(chain: OptionChain) -> float:
    """Quick "headline" IV: closest-to-spot strike, average of CE & PE IVs."""
    if not chain.rows:
        return 0.0
    spot = float(chain.spot)
    closest = min(chain.rows, key=lambda r: abs(float(r.strike) - spot))
    call_iv = closest.call.iv if closest.call else 0.0
    put_iv = closest.put.iv if closest.put else 0.0
    if call_iv and put_iv:
        return (call_iv + put_iv) / 2
    return call_iv or put_iv
