"""Option chain assembly.

Given a symbol + expiry, fetch the strike grid from the broker, run Greeks
& IV through Black-Scholes, and return a unified ``OptionChain`` with one
row per strike (CE + PE side-by-side).

Brokers don't expose a uniform option-chain endpoint, so this module
defines the shape and a default implementation that walks the
``Instrument`` table for matching CE/PE rows. Brokers that DO expose chains
natively can be plugged in later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.options.black_scholes import Greeks, greeks, implied_vol
from app.db.models.instrument import Instrument


@dataclass(frozen=True)
class OptionLeg:
    symbol: str
    strike: Decimal
    last_price: Decimal
    iv: float
    open_interest: int
    volume: int
    greeks: Greeks


@dataclass(frozen=True)
class OptionChainRow:
    strike: Decimal
    call: OptionLeg | None
    put: OptionLeg | None


@dataclass(frozen=True)
class OptionChain:
    underlying: str
    spot: Decimal
    expiry: date
    risk_free_rate: float
    rows: list[OptionChainRow] = field(default_factory=list)


async def list_strikes(
    session: AsyncSession,
    *,
    underlying: str,
    expiry: date,
    broker_id: str,
) -> list[Instrument]:
    """All Instrument rows whose tradingsymbol contains ``underlying`` and
    expiry matches. We rely on the broker's master contract sync having
    populated the table.
    """
    rows = (
        await session.execute(
            select(Instrument).where(
                Instrument.broker_id == broker_id,
                Instrument.expiry == expiry,
                Instrument.symbol.ilike(f"{underlying}%"),
                Instrument.instrument_type.in_(("CE", "PE")),
            )
        )
    ).scalars().all()
    return rows


async def build_chain(
    session: AsyncSession,
    *,
    underlying: str,
    expiry: date,
    broker_id: str,
    spot: Decimal,
    risk_free_rate: float = 0.07,
    quote_lookup: dict[str, dict] | None = None,
) -> OptionChain:
    """Compute IV + Greeks for every strike on a given expiry.

    ``quote_lookup`` is a ``{symbol: {last_price, oi, volume}}`` map the caller
    fetched from the broker. We pass it in so this module stays IO-free.
    """
    quote_lookup = quote_lookup or {}
    instruments = await list_strikes(
        session, underlying=underlying, expiry=expiry, broker_id=broker_id
    )
    by_strike: dict[Decimal, dict[str, Instrument]] = {}
    for inst in instruments:
        if inst.strike is None:
            continue
        side = "CE" if str(inst.instrument_type) == "CE" else "PE"
        by_strike.setdefault(inst.strike, {})[side] = inst

    today = datetime.utcnow().date()
    days_to_expiry = max((expiry - today).days, 0)
    T = days_to_expiry / 365.0 if days_to_expiry > 0 else 1 / 365.0

    rows: list[OptionChainRow] = []
    for strike in sorted(by_strike.keys()):
        legs: dict[str, OptionLeg | None] = {"CE": None, "PE": None}
        for side, inst in by_strike[strike].items():
            quote = quote_lookup.get(inst.symbol, {})
            last_price = float(quote.get("last_price", 0) or 0)
            oi = int(quote.get("oi", 0) or 0)
            volume = int(quote.get("volume", 0) or 0)
            iv = implied_vol(
                market_price=last_price,
                S=float(spot),
                K=float(strike),
                T=T,
                r=risk_free_rate,
                option_type=side,
            )
            iv = iv if iv == iv else 0.0  # NaN guard
            g = greeks(
                S=float(spot),
                K=float(strike),
                T=T,
                r=risk_free_rate,
                sigma=max(iv, 1e-4),
                option_type=side,
            )
            legs[side] = OptionLeg(
                symbol=inst.symbol,
                strike=strike,
                last_price=Decimal(str(last_price)),
                iv=iv,
                open_interest=oi,
                volume=volume,
                greeks=g,
            )
        rows.append(OptionChainRow(strike=strike, call=legs["CE"], put=legs["PE"]))
    return OptionChain(
        underlying=underlying,
        spot=spot,
        expiry=expiry,
        risk_free_rate=risk_free_rate,
        rows=rows,
    )
