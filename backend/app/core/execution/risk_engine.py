"""Pre-trade risk validation.

Every check returns a RiskCheckResult; ``validate`` short-circuits on the first
failure. Critical checks require real data:

- ``check_min_lot`` reads ``Instrument.lot_size`` (was previously hardcoded to 1).
- ``check_margin`` calls ``broker.get_margin()`` for live accounts (was a fake
  10-crore comparison).
- ``check_market_hours`` consults ``MarketHoliday`` and ``MarketSession``.
- ``check_qty_freeze`` consults ``QtyFreezeLimit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAdapter
from app.brokers.factory import BrokerFactory
from app.cache import keys
from app.config import get_settings
from app.db.models.account import Account
from app.db.models.calendar import MarketHoliday, MarketSession
from app.db.models.fundamentals import FundamentalSnapshot
from app.db.models.instrument import Instrument, QtyFreezeLimit
from app.db.models.position import Position
from app.infrastructure.logging import get_logger
from app.utils.time import utcnow

from .models import PlaceOrderRequest, RiskCheckResult, RiskValidationResult

logger = get_logger(__name__)

# 30 % single-symbol concentration cap; tweakable per account in the future.
DEFAULT_CONCENTRATION_CAP = Decimal("0.30")
ORDERS_PER_MINUTE_LIMIT = 20


@dataclass
class RiskEngine:
    session: AsyncSession
    redis: Redis
    broker_factory: BrokerFactory | None = None

    # ------------------------------------------------------------------ checks

    async def check_market_hours(self, exchange: str) -> RiskCheckResult:
        now = utcnow()
        holiday = await self.session.scalar(
            select(MarketHoliday).where(
                MarketHoliday.exchange == exchange,
                MarketHoliday.holiday_date == now.date(),
            )
        )
        if holiday:
            return RiskCheckResult(passed=False, reason="market_closed")

        sessions = (
            await self.session.execute(
                select(MarketSession).where(
                    MarketSession.exchange == exchange,
                    MarketSession.weekday == now.weekday(),
                )
            )
        ).scalars().all()
        # If no sessions are configured at all, default to "open" (dev-friendly);
        # in production seed the table on first run.
        if not sessions:
            return RiskCheckResult(passed=True)
        now_t = now.time().replace(tzinfo=None)
        for item in sessions:
            if item.open_time <= now_t <= item.close_time:
                return RiskCheckResult(passed=True)
        return RiskCheckResult(passed=False, reason="market_closed")

    async def get_instrument(
        self, symbol: str, exchange: str, broker_id: str
    ) -> Instrument | None:
        return await self.session.scalar(
            select(Instrument).where(
                Instrument.symbol == symbol,
                Instrument.exchange == exchange,
                Instrument.broker_id == broker_id,
            )
        )

    async def check_symbol_exists(
        self, symbol: str, exchange: str, broker_id: str
    ) -> tuple[RiskCheckResult, Instrument | None]:
        instrument = await self.get_instrument(symbol, exchange, broker_id)
        if instrument is None:
            return RiskCheckResult(passed=False, reason="symbol_not_found"), None
        return RiskCheckResult(passed=True), instrument

    async def check_qty_freeze(
        self, exchange: str, symbol: str, quantity: Decimal
    ) -> RiskCheckResult:
        freeze = await self.session.scalar(
            select(QtyFreezeLimit).where(
                QtyFreezeLimit.exchange == exchange,
                QtyFreezeLimit.symbol == symbol,
            )
        )
        if freeze and quantity > freeze.qty_freeze:
            return RiskCheckResult(passed=False, reason="qty_freeze_exceeded")
        return RiskCheckResult(passed=True)

    async def check_min_lot(self, quantity: Decimal, lot_size: int) -> RiskCheckResult:
        """Quantity must be a positive multiple of ``lot_size``."""
        if quantity <= 0:
            return RiskCheckResult(passed=False, reason="non_positive_quantity")
        if lot_size <= 1:
            return RiskCheckResult(passed=True)
        if quantity % Decimal(str(lot_size)) != 0:
            return RiskCheckResult(passed=False, reason="invalid_lot_size")
        return RiskCheckResult(passed=True)

    async def check_margin(
        self,
        account: Account,
        required_margin: Decimal,
        broker: BrokerAdapter | None = None,
    ) -> RiskCheckResult:
        """For paper accounts, always pass. For live accounts, query broker margin."""
        if account.is_paper:
            return RiskCheckResult(passed=True)
        if broker is None and self.broker_factory is None:
            # Defensive fallback — should not happen; signals a wiring bug.
            logger.warning("risk.margin.no_broker", account_id=str(account.id))
            return RiskCheckResult(passed=False, reason="margin_check_unavailable")
        if broker is None:
            assert self.broker_factory is not None
            broker = await self.broker_factory.create(account)
        try:
            details = await broker.get_margin()
        except Exception as exc:  # noqa: BLE001
            logger.warning("risk.margin.fetch_failed", error=str(exc))
            return RiskCheckResult(passed=False, reason="margin_check_failed")
        if required_margin > details.available_cash:
            return RiskCheckResult(passed=False, reason="insufficient_margin")
        return RiskCheckResult(passed=True)

    async def check_concentration(
        self, account: Account, symbol: str, new_qty: Decimal
    ) -> RiskCheckResult:
        positions = (
            await self.session.execute(select(Position).where(Position.account_id == account.id))
        ).scalars().all()
        existing_for_symbol = sum(
            (abs(p.quantity) for p in positions if p.symbol == symbol),
            Decimal("0"),
        )
        total_other = sum(
            (abs(p.quantity) for p in positions if p.symbol != symbol),
            Decimal("0"),
        )
        new_symbol_total = existing_for_symbol + abs(new_qty)
        grand_total = new_symbol_total + total_other
        if grand_total == 0:
            return RiskCheckResult(passed=True)
        ratio = new_symbol_total / grand_total
        if ratio > DEFAULT_CONCENTRATION_CAP:
            return RiskCheckResult(passed=False, reason="concentration_limit")
        return RiskCheckResult(passed=True)

    async def check_max_orders_per_minute(self, account: Account) -> RiskCheckResult:
        now_minute = int(utcnow().timestamp()) // 60
        bucket = f"{keys.ratelimit_orders(str(account.id))}:{now_minute}"
        current = await self.redis.get(bucket)
        if current is not None and int(current) >= ORDERS_PER_MINUTE_LIMIT:
            return RiskCheckResult(passed=False, reason="rate_limit")
        return RiskCheckResult(passed=True)

    async def check_max_positions(self, account: Account) -> RiskCheckResult:
        """Cap at ``settings.max_positions`` distinct equity positions.

        Aligns with the concentrated-portfolio philosophy behind the
        multibagger scanners (Harsh/Ashwin target ~20 names max).
        """
        settings = get_settings()
        positions = (
            await self.session.execute(
                select(Position).where(
                    Position.account_id == account.id,
                    Position.quantity != 0,
                )
            )
        ).scalars().all()
        distinct_symbols = {p.symbol for p in positions}
        if len(distinct_symbols) >= int(settings.max_positions):
            return RiskCheckResult(passed=False, reason="max_positions_reached")
        return RiskCheckResult(passed=True)

    async def check_sector_concentration(
        self, account: Account, symbol: str, new_qty: Decimal, price: Decimal,
    ) -> RiskCheckResult:
        """No single sector may exceed ``settings.sector_concentration_cap_pct``.

        Sector comes from ``FundamentalSnapshot.sector`` (latest row). If no
        fundamentals are available, the check passes (we don't have signal).
        """
        settings = get_settings()
        cap = Decimal(str(settings.sector_concentration_cap_pct)) / Decimal("100")
        new_fund = (
            await self.session.execute(
                select(FundamentalSnapshot)
                .where(FundamentalSnapshot.symbol == symbol)
                .order_by(FundamentalSnapshot.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if new_fund is None or new_fund.sector is None:
            return RiskCheckResult(passed=True)
        new_sector = new_fund.sector

        positions = (
            await self.session.execute(
                select(Position).where(Position.account_id == account.id)
            )
        ).scalars().all()
        sector_notional = Decimal("0")
        total_notional = Decimal("0")
        for p in positions:
            px = p.current_price or p.avg_cost or Decimal("0")
            notional = abs(p.quantity) * px
            total_notional += notional
            snap = (
                await self.session.execute(
                    select(FundamentalSnapshot)
                    .where(FundamentalSnapshot.symbol == p.symbol)
                    .order_by(FundamentalSnapshot.as_of_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snap is not None and snap.sector == new_sector:
                sector_notional += notional
        new_notional = abs(new_qty) * price
        proposed_sector = sector_notional + new_notional
        proposed_total = total_notional + new_notional
        if proposed_total == 0:
            return RiskCheckResult(passed=True)
        ratio = proposed_sector / proposed_total
        if ratio > cap:
            return RiskCheckResult(passed=False, reason="sector_concentration_exceeded")
        return RiskCheckResult(passed=True)

    # ------------------------------------------------------------------ orchestrator

    async def validate(
        self,
        account: Account,
        request: PlaceOrderRequest,
        *,
        broker: BrokerAdapter | None = None,
    ) -> RiskValidationResult:
        """Run all checks in order; first failure short-circuits."""
        check_market = await self.check_market_hours(request.exchange)
        if not check_market.passed:
            return RiskValidationResult(passed=False, reason=check_market.reason)

        symbol_check, instrument = await self.check_symbol_exists(
            request.symbol, request.exchange, account.broker_id
        )
        if not symbol_check.passed:
            return RiskValidationResult(passed=False, reason=symbol_check.reason)

        check_qf = await self.check_qty_freeze(request.exchange, request.symbol, request.quantity)
        if not check_qf.passed:
            return RiskValidationResult(passed=False, reason=check_qf.reason)

        lot_size = instrument.lot_size if instrument else 1
        check_lot = await self.check_min_lot(request.quantity, lot_size)
        if not check_lot.passed:
            return RiskValidationResult(passed=False, reason=check_lot.reason)

        notional = request.quantity * (request.price or Decimal("0"))
        check_m = await self.check_margin(account, notional, broker=broker)
        if not check_m.passed:
            return RiskValidationResult(passed=False, reason=check_m.reason)

        check_c = await self.check_concentration(account, request.symbol, request.quantity)
        if not check_c.passed:
            return RiskValidationResult(passed=False, reason=check_c.reason)

        # Multibagger additions: max-positions + sector concentration.
        if request.side == "BUY":
            check_max_p = await self.check_max_positions(account)
            if not check_max_p.passed:
                return RiskValidationResult(passed=False, reason=check_max_p.reason)
            check_sector = await self.check_sector_concentration(
                account, request.symbol, request.quantity, request.price or Decimal("0"),
            )
            if not check_sector.passed:
                return RiskValidationResult(passed=False, reason=check_sector.reason)

        check_r = await self.check_max_orders_per_minute(account)
        if not check_r.passed:
            return RiskValidationResult(passed=False, reason=check_r.reason)

        return RiskValidationResult(passed=True)
