"""Options REST API.

All endpoints require auth and an explicit ``account_id`` so we know which
broker's master contract to read. Quotes for OI/volume must be fetched up
front via ``broker.get_quotes`` and passed into the chain builder so this
module stays free of broker calls.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_broker_factory
from app.brokers.factory import BrokerFactory
from app.core.auth.dependencies import get_current_user
from app.core.options import iv_analytics, oi_analytics, option_chain
from app.db.models.account import Account
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter()


@router.get("/options/chain")
async def get_chain(
    account_id: UUID,
    underlying: str,
    expiry: date,
    spot: Decimal,
    risk_free_rate: float = 0.07,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    factory: BrokerFactory = Depends(get_broker_factory),
) -> dict:
    """Return the full option chain (CE + PE per strike) with IV + Greeks."""
    account = await _resolve_account(session, account_id, user)

    instruments = await option_chain.list_strikes(
        session, underlying=underlying, expiry=expiry, broker_id=account.broker_id
    )
    quote_lookup: dict[str, dict] = {}
    if instruments:
        broker = await factory.create(account)
        try:
            quotes = await broker.get_quotes([(i.symbol, str(i.exchange)) for i in instruments])
            for (sym, _exch), q in quotes.items():
                quote_lookup[sym] = {"last_price": str(q.last_price)}
        except NotImplementedError:
            # Broker hasn't implemented bulk quotes yet — chain still
            # computes intrinsic values + zero IV/OI gracefully.
            pass

    chain = await option_chain.build_chain(
        session,
        underlying=underlying,
        expiry=expiry,
        broker_id=account.broker_id,
        spot=spot,
        risk_free_rate=risk_free_rate,
        quote_lookup=quote_lookup,
    )
    return _chain_to_dict(chain)


@router.get("/options/oi-profile")
async def get_oi_profile(
    account_id: UUID,
    underlying: str,
    expiry: date,
    spot: Decimal,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    factory: BrokerFactory = Depends(get_broker_factory),
) -> dict:
    chain = await _build_chain_helper(
        session, factory, account_id, user, underlying, expiry, spot
    )
    profile = oi_analytics.oi_profile(chain)
    summary = oi_analytics.summarise(chain)
    return {
        "underlying": underlying,
        "expiry": expiry.isoformat(),
        "summary": {
            "pcr_oi": summary.pcr_oi,
            "pcr_volume": summary.pcr_volume,
            "max_call_oi_strike": str(summary.max_call_oi_strike) if summary.max_call_oi_strike else None,
            "max_put_oi_strike": str(summary.max_put_oi_strike) if summary.max_put_oi_strike else None,
            "total_gex": summary.total_gex,
        },
        "rows": [
            {
                "strike": str(p.strike),
                "call_oi": p.call_oi,
                "put_oi": p.put_oi,
                "call_volume": p.call_volume,
                "put_volume": p.put_volume,
                "gex": p.gex,
            }
            for p in profile
        ],
    }


@router.get("/options/iv-smile")
async def get_iv_smile(
    account_id: UUID,
    underlying: str,
    expiry: date,
    spot: Decimal,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    factory: BrokerFactory = Depends(get_broker_factory),
) -> dict:
    chain = await _build_chain_helper(
        session, factory, account_id, user, underlying, expiry, spot
    )
    points = iv_analytics.iv_smile(chain)
    return {
        "underlying": underlying,
        "expiry": expiry.isoformat(),
        "atm_iv": iv_analytics.atm_iv(chain),
        "points": [
            {
                "strike": str(p.strike),
                "call_iv": p.call_iv,
                "put_iv": p.put_iv,
                "moneyness": p.moneyness,
            }
            for p in points
        ],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_account(session: AsyncSession, account_id: UUID, user: User) -> Account:
    account = await session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(404, "account_not_found")
    return account


async def _build_chain_helper(
    session: AsyncSession,
    factory: BrokerFactory,
    account_id: UUID,
    user: User,
    underlying: str,
    expiry: date,
    spot: Decimal,
):
    account = await _resolve_account(session, account_id, user)
    instruments = await option_chain.list_strikes(
        session, underlying=underlying, expiry=expiry, broker_id=account.broker_id
    )
    quote_lookup: dict[str, dict] = {}
    if instruments:
        broker = await factory.create(account)
        try:
            quotes = await broker.get_quotes([(i.symbol, str(i.exchange)) for i in instruments])
            for (sym, _exch), q in quotes.items():
                quote_lookup[sym] = {"last_price": str(q.last_price)}
        except NotImplementedError:
            pass
    return await option_chain.build_chain(
        session,
        underlying=underlying,
        expiry=expiry,
        broker_id=account.broker_id,
        spot=spot,
        quote_lookup=quote_lookup,
    )


def _chain_to_dict(chain) -> dict:
    return {
        "underlying": chain.underlying,
        "spot": str(chain.spot),
        "expiry": chain.expiry.isoformat(),
        "risk_free_rate": chain.risk_free_rate,
        "rows": [
            {
                "strike": str(row.strike),
                "call": _leg_to_dict(row.call) if row.call else None,
                "put": _leg_to_dict(row.put) if row.put else None,
            }
            for row in chain.rows
        ],
    }


def _leg_to_dict(leg) -> dict:
    return {
        "symbol": leg.symbol,
        "last_price": str(leg.last_price),
        "iv": leg.iv,
        "open_interest": leg.open_interest,
        "volume": leg.volume,
        "greeks": {
            "delta": leg.greeks.delta,
            "gamma": leg.greeks.gamma,
            "theta": leg.greeks.theta,
            "vega": leg.greeks.vega,
            "rho": leg.greeks.rho,
            "price": leg.greeks.price,
        },
    }
