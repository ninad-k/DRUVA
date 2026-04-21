"""Market cycle regime controller.

Reads daily Nifty50 / SmallCap100 candles, computes 18m / 20m ROC on
monthly resamples, classifies regime:

- ``bull``    — both ROC > 0 and small-cap outperforms Nifty
- ``neutral`` — Nifty ROC > 0 but small-cap ROC <= 0 (stock-pickers market)
- ``bear``    — both ROC <= 0

and upserts today's ``MarketCycleState`` row.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.market_cycle import MarketCycleState, MarketRegime
from app.strategies.indicators.roc import resample_monthly, roc
from app.utils.time import utcnow

NIFTY_SYMBOL = "NIFTY 50"
SMALLCAP_SYMBOL = "NIFTY SMLCAP 100"
INDEX_EXCHANGE = "NSE"


@dataclass
class MarketCycleResult:
    regime: MarketRegime
    nifty_roc: Decimal | None
    smallcap_roc: Decimal | None
    suggested_allocation_pct: Decimal


def classify(
    nifty_roc: Decimal | None,
    smallcap_roc: Decimal | None,
    settings: Settings,
) -> MarketCycleResult:
    if nifty_roc is None or smallcap_roc is None:
        return MarketCycleResult(
            regime=MarketRegime.NEUTRAL,
            nifty_roc=nifty_roc,
            smallcap_roc=smallcap_roc,
            suggested_allocation_pct=Decimal(str(settings.market_cycle_neutral_pct)),
        )

    if nifty_roc > 0 and smallcap_roc > nifty_roc:
        return MarketCycleResult(
            regime=MarketRegime.BULL,
            nifty_roc=nifty_roc,
            smallcap_roc=smallcap_roc,
            suggested_allocation_pct=Decimal(str(settings.market_cycle_bull_pct)),
        )
    if nifty_roc > 0 and smallcap_roc <= 0:
        return MarketCycleResult(
            regime=MarketRegime.NEUTRAL,
            nifty_roc=nifty_roc,
            smallcap_roc=smallcap_roc,
            suggested_allocation_pct=Decimal(str(settings.market_cycle_neutral_pct)),
        )
    if nifty_roc <= 0 and smallcap_roc <= 0:
        return MarketCycleResult(
            regime=MarketRegime.BEAR,
            nifty_roc=nifty_roc,
            smallcap_roc=smallcap_roc,
            suggested_allocation_pct=Decimal(str(settings.market_cycle_bear_pct)),
        )
    # Mixed positive/negative fallthrough — treat as neutral.
    return MarketCycleResult(
        regime=MarketRegime.NEUTRAL,
        nifty_roc=nifty_roc,
        smallcap_roc=smallcap_roc,
        suggested_allocation_pct=Decimal(str(settings.market_cycle_neutral_pct)),
    )


@dataclass
class MarketCycleRegimeDetector:
    session: AsyncSession
    settings: Settings = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_settings()

    async def compute(self) -> MarketCycleResult:
        repo = OhlcvRepository(session=self.session)
        nifty_daily = await repo.latest(
            symbol=NIFTY_SYMBOL, exchange=INDEX_EXCHANGE, timeframe="1d", limit=600,
        )
        small_daily = await repo.latest(
            symbol=SMALLCAP_SYMBOL, exchange=INDEX_EXCHANGE, timeframe="1d", limit=600,
        )
        nifty_monthly = resample_monthly(nifty_daily)
        small_monthly = resample_monthly(small_daily)
        nifty_roc = roc(nifty_monthly, 18)
        small_roc = roc(small_monthly, 20)
        return classify(nifty_roc, small_roc, self.settings)

    async def upsert_today(self, result: MarketCycleResult) -> MarketCycleState:
        today = utcnow().date()
        row = (
            await self.session.execute(
                select(MarketCycleState).where(MarketCycleState.as_of_date == today)
            )
        ).scalar_one_or_none()
        if row is None:
            row = MarketCycleState(as_of_date=today)
            self.session.add(row)
        row.regime = result.regime
        row.nifty_roc_18m = result.nifty_roc
        row.smallcap_roc_20m = result.smallcap_roc
        row.suggested_allocation_pct = result.suggested_allocation_pct
        await self.session.commit()
        return row
