"""Idempotent demo-data seed script.

Creates a fully-populated demo user so the platform can be explored without
a live broker connection.  Run from the ``backend/`` directory:

    python -m app.scripts.seed_demo

The script is safe to run multiple times — it skips rows that already exist
and never deletes existing data.

Demo credentials
----------------
  Email:    demo@dhruva.dev
  Password: DhruvaDemo123!
  Role:     (standard user; admin login uses the DEV_ADMIN_* env vars)
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
import uuid
from datetime import date, timedelta
from decimal import Decimal

from datetime import time as dtime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.password import PasswordService
from app.db.models.account import Account
from app.db.models.calendar import MarketSession
from app.db.models.common import (
    Exchange,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductType,
    SessionType,
    StrategyMode,
)
from app.db.models.goal import GoalStatus, InvestmentGoal, SipSchedule
from app.db.models.scanner import ScannerCadence, ScanResultStatus
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.scanner import ScanResult, ScannerConfig
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.models.watchlist import Watchlist, WatchlistItem
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Demo constants
# ---------------------------------------------------------------------------

DEMO_EMAIL = "demo@dhruva.dev"
DEMO_PASSWORD = "DhruvaDemo123!"
DEMO_USERNAME = "demo"
DEMO_DISPLAY = "Demo Trader"

# A stable master key for demo (32 bytes, base64-encoded).
# In production, DHRUVA_MASTER_KEY must be a real secret.
_DEMO_MASTER_KEY_B64: str = base64.b64encode(b"demo-key-NOT-secure-32-bytes-pad").decode()

NIFTY50_WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
    "HINDUNILVR", "ITC", "SBIN", "BAJFINANCE", "KOTAKBANK",
    "AXISBANK", "MARUTI", "WIPRO", "LT", "ULTRACEMCO",
    "ADANIENT", "ASIANPAINT", "TITAN", "SUNPHARMA", "NESTLEIND",
]

# Sectors mapped to symbols for diversified demo positions
DEMO_POSITIONS = [
    # (symbol, exchange, qty, avg_cost, realized_pnl)
    ("RELIANCE",    Exchange.NSE, Decimal("50"),  Decimal("2850.00"), Decimal("3200.00")),
    ("TCS",         Exchange.NSE, Decimal("30"),  Decimal("3600.00"), Decimal("1800.00")),
    ("HDFCBANK",    Exchange.NSE, Decimal("80"),  Decimal("1650.00"), Decimal("-900.00")),
    ("INFY",        Exchange.NSE, Decimal("60"),  Decimal("1750.00"), Decimal("2400.00")),
    ("ITC",         Exchange.NSE, Decimal("200"), Decimal("450.00"),  Decimal("1200.00")),
    ("MARUTI",      Exchange.NSE, Decimal("10"),  Decimal("10200.00"),Decimal("5000.00")),
    ("SUNPHARMA",   Exchange.NSE, Decimal("40"),  Decimal("1300.00"), Decimal("-600.00")),
    ("AXISBANK",    Exchange.NSE, Decimal("100"), Decimal("1050.00"), Decimal("3500.00")),
    ("BAJFINANCE",  Exchange.NSE, Decimal("20"),  Decimal("7100.00"), Decimal("4200.00")),
    ("TITAN",       Exchange.NSE, Decimal("25"),  Decimal("3400.00"), Decimal("2100.00")),
]

# Recent order history
DEMO_ORDERS: list[tuple] = [
    # (symbol, side, qty, price, status, tag)
    ("RELIANCE",  OrderSide.BUY,  Decimal("50"),  Decimal("2850.00"), OrderStatus.FILLED,     "hmm_regime"),
    ("TCS",       OrderSide.BUY,  Decimal("30"),  Decimal("3600.00"), OrderStatus.FILLED,     "hmm_regime"),
    ("HDFCBANK",  OrderSide.BUY,  Decimal("80"),  Decimal("1650.00"), OrderStatus.FILLED,     "manual"),
    ("INFY",      OrderSide.BUY,  Decimal("60"),  Decimal("1750.00"), OrderStatus.FILLED,     "hmm_regime"),
    ("WIPRO",     OrderSide.BUY,  Decimal("40"),  Decimal("550.00"),  OrderStatus.CANCELLED,  "manual"),
    ("ITC",       OrderSide.BUY,  Decimal("200"), Decimal("450.00"),  OrderStatus.FILLED,     "manual"),
    ("MARUTI",    OrderSide.BUY,  Decimal("10"),  Decimal("10200.00"),OrderStatus.FILLED,     "vcp_scanner"),
    ("SUNPHARMA", OrderSide.BUY,  Decimal("40"),  Decimal("1300.00"), OrderStatus.FILLED,     "manual"),
    ("AXISBANK",  OrderSide.BUY,  Decimal("100"), Decimal("1050.00"), OrderStatus.FILLED,     "hmm_regime"),
    ("BAJFINANCE",OrderSide.BUY,  Decimal("20"),  Decimal("7100.00"), OrderStatus.FILLED,     "vcp_scanner"),
    ("TITAN",     OrderSide.BUY,  Decimal("25"),  Decimal("3400.00"), OrderStatus.FILLED,     "manual"),
    ("WIPRO",     OrderSide.SELL, Decimal("30"),  Decimal("590.00"),  OrderStatus.FILLED,     "hmm_regime"),
    ("ICICIBANK", OrderSide.BUY,  Decimal("50"),  Decimal("1200.00"), OrderStatus.REJECTED,   "hmm_regime"),
    ("KOTAKBANK", OrderSide.BUY,  Decimal("25"),  Decimal("1900.00"), OrderStatus.CANCELLED,  "manual"),
    ("LT",        OrderSide.BUY,  Decimal("15"),  Decimal("3700.00"), OrderStatus.PENDING,    "manual"),
]

DEMO_SCAN_SYMBOLS = [
    ("NESTLEIND",  Decimal("87.5"), "Stage 2"),
    ("ASIANPAINT", Decimal("76.2"), "Stage 2"),
    ("PIDILITIND", Decimal("71.8"), "Stage 2"),
    ("BAJAJFINSV", Decimal("68.3"), "Stage 1"),
    ("TRENT",      Decimal("92.1"), "Stage 2"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_encrypted_blob() -> tuple[str, str]:
    """Return (ciphertext_b64, nonce_b64) with placeholder demo credentials."""
    nonce = secrets.token_bytes(12)
    # Demo mode — store dummy encrypted content (broker won't be called)
    payload = b"DEMO_CREDENTIAL_PLACEHOLDER"
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key = base64.b64decode(_DEMO_MASTER_KEY_B64)
    ciphertext = AESGCM(key).encrypt(nonce, payload, None)
    return (
        base64.b64encode(ciphertext).decode(),
        base64.b64encode(nonce).decode(),
    )


async def _get_or_create_user(session: AsyncSession) -> User:
    result = await session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if result:
        logger.info("seed.user_exists", email=DEMO_EMAIL)
        return result

    pw = PasswordService()
    user = User(
        email=DEMO_EMAIL,
        username=DEMO_USERNAME,
        display_name=DEMO_DISPLAY,
        password_hash=pw.hash(DEMO_PASSWORD),
        is_active=True,
    )
    session.add(user)
    await session.flush()
    logger.info("seed.user_created", email=DEMO_EMAIL, id=str(user.id))
    return user


async def _get_or_create_account(session: AsyncSession, user: User) -> Account:
    result = await session.scalar(
        select(Account).where(Account.user_id == user.id, Account.broker_id == "paper")
    )
    if result:
        logger.info("seed.account_exists", broker="paper")
        return result

    ct, nonce = _fake_encrypted_blob()
    account = Account(
        user_id=user.id,
        broker_id="paper",
        account_ref="DEMO001",
        api_key_encrypted=ct,
        api_key_nonce=nonce,
        api_secret_encrypted=ct,
        api_secret_nonce=nonce,
        is_active=True,
        is_paper=True,
        default_product=ProductType.CNC,
        paper_starting_capital=Decimal("5000000"),  # ₹50 lakh
    )
    session.add(account)
    await session.flush()
    logger.info("seed.account_created", id=str(account.id))
    return account


async def _seed_watchlist(session: AsyncSession, account: Account) -> None:
    existing = await session.scalar(
        select(Watchlist).where(Watchlist.account_id == account.id, Watchlist.name == "NIFTY 50 Core")
    )
    if existing:
        logger.info("seed.watchlist_exists")
        return

    wl = Watchlist(
        account_id=account.id,
        name="NIFTY 50 Core",
        description="Top NIFTY-50 stocks tracked daily",
        is_default=True,
    )
    session.add(wl)
    await session.flush()

    for symbol in NIFTY50_WATCHLIST:
        session.add(WatchlistItem(watchlist_id=wl.id, symbol=symbol, exchange="NSE"))
    logger.info("seed.watchlist_created", symbols=len(NIFTY50_WATCHLIST))


async def _seed_positions(session: AsyncSession, account: Account) -> None:
    for symbol, exchange, qty, avg_cost, realized_pnl in DEMO_POSITIONS:
        existing = await session.scalar(
            select(Position).where(
                Position.account_id == account.id,
                Position.symbol == symbol,
                Position.exchange == exchange,
            )
        )
        if existing:
            continue
        session.add(Position(
            account_id=account.id,
            symbol=symbol,
            exchange=exchange,
            product=ProductType.CNC,
            quantity=qty,
            avg_cost=avg_cost,
            realized_pnl=realized_pnl,
        ))
    logger.info("seed.positions_done", count=len(DEMO_POSITIONS))


async def _seed_orders(session: AsyncSession, user: User, account: Account) -> None:
    count = 0
    for symbol, side, qty, price, status, tag in DEMO_ORDERS:
        session.add(Order(
            user_id=user.id,
            account_id=account.id,
            symbol=symbol,
            exchange=Exchange.NSE,
            side=side,
            quantity=qty,
            filled_quantity=qty if status == OrderStatus.FILLED else Decimal("0"),
            order_type=OrderType.LIMIT,
            product=ProductType.CNC,
            price=price,
            status=status,
            tag=tag,
        ))
        count += 1
    logger.info("seed.orders_done", count=count)


async def _seed_strategies(session: AsyncSession, account: Account) -> Strategy:
    strategies_data = [
        ("HMM Regime Trader", "strategies.ml.regime_trader.RegimeTraderStrategy",
         {"n_regimes": 5, "lookback_days": 252}, True),
        ("VCP Momentum", "strategies.scanners.vcp.VcpMomentumStrategy",
         {"atr_multiplier": 2.0, "volume_threshold": 1.5}, False),
        ("Mean Reversion Bands", "strategies.options.mean_reversion.MeanReversionBands",
         {"bb_period": 20, "bb_std": 2.0, "rsi_oversold": 30}, False),
    ]
    primary_strategy = None
    for name, cls, params, is_ml in strategies_data:
        existing = await session.scalar(
            select(Strategy).where(Strategy.account_id == account.id, Strategy.name == name)
        )
        if existing:
            if primary_strategy is None:
                primary_strategy = existing
            continue
        strat = Strategy(
            account_id=account.id,
            name=name,
            strategy_class=cls,
            parameters=params,
            mode=StrategyMode.PAPER,
            is_ml=is_ml,
            is_enabled=True,
        )
        session.add(strat)
        await session.flush()
        if primary_strategy is None:
            primary_strategy = strat
    logger.info("seed.strategies_done")
    return primary_strategy  # type: ignore[return-value]


async def _seed_goals(session: AsyncSession, account: Account, strategy: Strategy) -> None:
    goals_data = [
        (
            "Retirement Corpus",
            Decimal("50000000"),  # ₹5 cr
            date.today().replace(year=date.today().year + 15),
            Decimal("25000"),
            Decimal("8000000"),   # current value
            Decimal("70"),        # equity %
        ),
        (
            "Child Education Fund",
            Decimal("5000000"),   # ₹50 lakh
            date.today().replace(year=date.today().year + 8),
            Decimal("15000"),
            Decimal("1200000"),
            Decimal("60"),
        ),
    ]
    for name, target, target_date, sip, current, equity_pct in goals_data:
        existing = await session.scalar(
            select(InvestmentGoal).where(
                InvestmentGoal.account_id == account.id, InvestmentGoal.name == name
            )
        )
        if existing:
            continue
        goal = InvestmentGoal(
            account_id=account.id,
            name=name,
            target_amount=target,
            target_date=target_date,
            current_value=current,
            monthly_sip_amount=sip,
            arbitrage_buffer_pct=Decimal("5"),
            equity_allocation_pct=equity_pct,
            status=GoalStatus.ACTIVE,
            target_symbols=["NIFTYBEES", "GOLDBEES", "LIQUIDBEES"],
        )
        session.add(goal)
        await session.flush()
        sip_sched = SipSchedule(
            goal_id=goal.id,
            strategy_id=strategy.id,
            day_of_month=5,
            next_run_date=date.today().replace(day=5) + timedelta(days=30),
            is_active=True,
        )
        session.add(sip_sched)
    logger.info("seed.goals_done")


async def _seed_scanner(session: AsyncSession, account: Account) -> None:
    existing = await session.scalar(
        select(ScannerConfig).where(
            ScannerConfig.account_id == account.id, ScannerConfig.name == "VCP Scanner"
        )
    )
    if existing:
        scanner = existing
    else:
        scanner = ScannerConfig(
            account_id=account.id,
            name="VCP Scanner",
            scanner_class="app.strategies.scanners.vcp.VcpScanner",
            parameters={"min_tightness_pct": 15.0, "volume_dry_up": 0.7},
            cadence=ScannerCadence.DAILY,
            is_enabled=True,
        )
        session.add(scanner)
        await session.flush()
        logger.info("seed.scanner_created")

    # Seed recent scan results
    from datetime import datetime, timezone
    for symbol, score, stage in DEMO_SCAN_SYMBOLS:
        session.add(ScanResult(
            scanner_id=scanner.id,
            run_ts=datetime.now(timezone.utc),
            symbol=symbol,
            exchange="NSE",
            score=score,
            stage=stage,
            status=ScanResultStatus.NEW,
        ))
    logger.info("seed.scan_results_done", count=len(DEMO_SCAN_SYMBOLS))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _seed_market_calendar(session: AsyncSession) -> None:
    """Seed NSE/BSE regular sessions if the table is empty.

    Times are stored in UTC (09:15-15:30 IST → 03:45-10:00 UTC) — matches
    scripts/seed_market_calendar.py. Without these rows the dashboard's
    "NSE Open / NSE Closed" badge defaults to closed.
    """
    existing = await session.scalar(select(MarketSession).limit(1))
    if existing is not None:
        logger.info("seed.market_sessions_exist")
        return
    sessions_open = dtime(3, 45)
    sessions_close = dtime(10, 0)
    for exchange in (Exchange.NSE, Exchange.BSE):
        for weekday in range(5):  # Mon-Fri
            session.add(
                MarketSession(
                    exchange=exchange,
                    weekday=weekday,
                    open_time=sessions_open,
                    close_time=sessions_close,
                    session_type=SessionType.REGULAR,
                )
            )
    logger.info("seed.market_sessions_created")


async def seed() -> None:
    async with SessionLocal() as session:
        async with session.begin():
            await _seed_market_calendar(session)
            user = await _get_or_create_user(session)
            account = await _get_or_create_account(session, user)
            await _seed_watchlist(session, account)
            await _seed_positions(session, account)
            await _seed_orders(session, user, account)
            strategy = await _seed_strategies(session, account)
            await _seed_goals(session, account, strategy)
            await _seed_scanner(session, account)

    print("\n" + "=" * 60)
    print("  DHRUVA Demo Data Seeded Successfully")
    print("=" * 60)
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print(f"  Broker:   Paper trading (₹50L starting capital)")
    print(f"  Data:     {len(DEMO_POSITIONS)} positions | {len(DEMO_ORDERS)} orders")
    print(f"            {len(NIFTY50_WATCHLIST)} watchlist symbols")
    print(f"            3 strategies | 2 goals | 1 scanner")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(seed())
