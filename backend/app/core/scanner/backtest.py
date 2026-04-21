"""Scanner backtest engine.

Replays the chosen date range day-by-day. For each trading day:
- Truncate the OHLCV universe to bars up to that day.
- Invoke ``scanner.scan()`` with a frozen-in-time context.
- Simulate entry at next-day open for each emitted candidate.
- Trail by 21-EMA, exit on stop or EMA cross.
- Aggregate equity curve, CAGR, Sharpe, max DD, multibagger distribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.scanner.base import (
    FundamentalSnapshotDTO,
    InstrumentRef,
    MarketCycleDTO,
    ScanCandidate,
    Scanner,
)
from app.core.scanner.registry import get_scanner_class
from app.data.fundamentals.repository import FundamentalRepository
from app.data.ohlcv_repository import OhlcvRepository
from app.db.models.fundamentals import FundamentalSnapshot  # noqa: F401 — metadata register
from app.strategies.base import Candle
from app.strategies.indicators.vcp import trailing_ema_stop


@dataclass
class BacktestTrade:
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal
    return_pct: Decimal
    hold_days: int


@dataclass
class BacktestMetrics:
    total_return_pct: Decimal
    cagr_pct: Decimal
    sharpe: Decimal
    max_drawdown_pct: Decimal
    win_rate_pct: Decimal
    avg_hold_days: Decimal
    trades: int
    multibagger_2x: int
    multibagger_5x: int
    multibagger_10x: int


@dataclass
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: list[tuple[datetime, Decimal]]
    trades: list[BacktestTrade] = field(default_factory=list)


@dataclass
class _FrozenCtx:
    """Frozen-in-time context for backtest replay."""

    session: AsyncSession
    account_id: Any
    as_of: date
    _candles_cache: dict[tuple[str, str], list[Candle]]
    _universe: list[InstrumentRef]
    _emitted: list[ScanCandidate]

    async def get_universe(self, filters: dict[str, Any] | None = None) -> list[InstrumentRef]:
        return self._universe

    async def get_candles(
        self, symbol: str, exchange: str, timeframe: str, limit: int,
    ) -> list[Candle]:
        key = (symbol, exchange)
        full = self._candles_cache.get(key)
        if full is None:
            repo = OhlcvRepository(session=self.session)
            full = await repo.latest(
                symbol=symbol, exchange=exchange, timeframe=timeframe, limit=2000,
            )
            self._candles_cache[key] = full
        truncated = [c for c in full if c.ts.date() <= self.as_of]
        return truncated[-limit:]

    async def get_fundamentals(
        self, symbol: str, exchange: str,
    ) -> FundamentalSnapshotDTO | None:
        repo = FundamentalRepository(session=self.session)
        row = await repo.as_of(symbol=symbol, exchange=exchange, as_of=self.as_of)
        if row is None:
            return None
        return FundamentalSnapshotDTO(
            symbol=row.symbol,
            exchange=row.exchange,
            roe=row.roe,
            roce=row.roce,
            eps=row.eps,
            sales_growth_3y=row.sales_growth_3y,
            profit_growth_3y=row.profit_growth_3y,
            debt_to_equity=row.debt_to_equity,
            promoter_holding=row.promoter_holding,
            market_cap=row.market_cap,
            pe_ratio=row.pe_ratio,
            sector=row.sector,
            industry=row.industry,
        )

    async def get_market_cycle(self) -> MarketCycleDTO | None:
        # For simplicity the backtest defaults to neutral regime. Phase 5
        # extension will add a historical MarketCycleState lookup.
        return MarketCycleDTO(
            regime="neutral",
            nifty_roc_18m=None,
            smallcap_roc_20m=None,
            suggested_allocation_pct=Decimal("60"),
        )

    async def emit(self, candidate: ScanCandidate) -> None:
        self._emitted.append(candidate)


@dataclass
class ScannerBacktestEngine:
    session: AsyncSession

    async def run(
        self,
        *,
        scanner_class: str,
        parameters: dict[str, Any],
        start: date,
        end: date,
        universe: list[InstrumentRef] | None = None,
        initial_equity: Decimal = Decimal("1000000"),
        step_days: int = 7,
    ) -> BacktestResult:
        cls = get_scanner_class(scanner_class)
        scanner: Scanner = cls(parameters=parameters)
        if universe is None:
            from app.core.scanner.universe import UniverseProvider

            universe = await UniverseProvider(session=self.session).list()

        open_positions: dict[str, tuple[date, Decimal]] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[datetime, Decimal]] = []
        equity = initial_equity

        cache: dict[tuple[str, str], list[Candle]] = {}
        d = start
        while d <= end:
            ctx = _FrozenCtx(
                session=self.session,
                account_id=None,
                as_of=d,
                _candles_cache=cache,
                _universe=universe,
                _emitted=[],
            )
            try:
                candidates = await scanner.scan(ctx)
            except Exception:  # noqa: BLE001
                candidates = []
            all_cands = list(ctx._emitted) + list(candidates)

            # Exit step — trail stop by 21-EMA.
            to_close: list[str] = []
            for sym, (entry_d, entry_px) in list(open_positions.items()):
                key = (sym, "NSE")
                full = cache.get(key, [])
                series = [c for c in full if c.ts.date() <= d]
                if not series:
                    continue
                last_px = Decimal(str(series[-1].close))
                ema_stop = trailing_ema_stop(series, 21)
                if ema_stop is None:
                    continue
                if last_px < ema_stop:
                    pnl = last_px - entry_px
                    ret = (pnl / entry_px * Decimal("100")) if entry_px > 0 else Decimal("0")
                    trades.append(
                        BacktestTrade(
                            symbol=sym,
                            entry_date=entry_d,
                            exit_date=d,
                            entry_price=entry_px,
                            exit_price=last_px,
                            pnl=pnl,
                            return_pct=ret,
                            hold_days=(d - entry_d).days,
                        )
                    )
                    equity += pnl
                    to_close.append(sym)
            for sym in to_close:
                del open_positions[sym]

            # Entry step — next-day open on each new candidate.
            for cand in all_cands:
                if cand.symbol in open_positions or cand.symbol == "__PORTFOLIO__":
                    continue
                if len(open_positions) >= 20:
                    break
                key = (cand.symbol, cand.exchange)
                series = cache.get(key, [])
                series = [c for c in series if c.ts.date() > d]
                if not series:
                    continue
                entry_px = Decimal(str(series[0].open))
                open_positions[cand.symbol] = (series[0].ts.date(), entry_px)

            equity_curve.append((datetime.combine(d, datetime.min.time()), equity))
            d = d + timedelta(days=step_days)

        # Close any dangling positions at the end at last close.
        for sym, (entry_d, entry_px) in open_positions.items():
            key = (sym, "NSE")
            full = cache.get(key, [])
            if not full:
                continue
            last_px = Decimal(str(full[-1].close))
            pnl = last_px - entry_px
            ret = (pnl / entry_px * Decimal("100")) if entry_px > 0 else Decimal("0")
            trades.append(
                BacktestTrade(
                    symbol=sym,
                    entry_date=entry_d,
                    exit_date=end,
                    entry_price=entry_px,
                    exit_price=last_px,
                    pnl=pnl,
                    return_pct=ret,
                    hold_days=(end - entry_d).days,
                )
            )

        return BacktestResult(
            metrics=_compute_metrics(trades, equity_curve, initial_equity, start, end),
            equity_curve=equity_curve,
            trades=trades,
        )


def _compute_metrics(
    trades: list[BacktestTrade],
    equity_curve: list[tuple[datetime, Decimal]],
    initial: Decimal,
    start: date,
    end: date,
) -> BacktestMetrics:
    if not trades:
        return BacktestMetrics(
            total_return_pct=Decimal("0"),
            cagr_pct=Decimal("0"),
            sharpe=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
            win_rate_pct=Decimal("0"),
            avg_hold_days=Decimal("0"),
            trades=0,
            multibagger_2x=0,
            multibagger_5x=0,
            multibagger_10x=0,
        )
    final_equity = equity_curve[-1][1] if equity_curve else initial
    total_ret = ((final_equity - initial) / initial * Decimal("100")) if initial > 0 else Decimal("0")
    years = max(Decimal("0.01"), Decimal((end - start).days) / Decimal("365.25"))
    ratio = final_equity / initial if initial > 0 else Decimal("1")
    # CAGR = ratio^(1/years) - 1. Use float for pow.
    try:
        cagr = (float(ratio) ** (1.0 / float(years)) - 1.0) * 100.0
    except Exception:  # noqa: BLE001
        cagr = 0.0
    wins = [t for t in trades if t.pnl > 0]
    win_rate = Decimal(len(wins)) / Decimal(len(trades)) * Decimal("100")
    avg_hold = Decimal(sum((t.hold_days for t in trades), 0)) / Decimal(len(trades))

    # Simple Sharpe on trade returns.
    rets = [float(t.return_pct) for t in trades]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    std = var ** 0.5
    sharpe = Decimal(str((mean / std) if std > 0 else 0.0)).quantize(Decimal("0.001"))

    # Max drawdown on equity curve.
    peak = initial
    max_dd = Decimal("0")
    for _, e in equity_curve:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak * Decimal("100")
            if dd > max_dd:
                max_dd = dd

    def _mb(mult: Decimal) -> int:
        return sum(1 for t in trades if t.entry_price > 0 and t.exit_price / t.entry_price >= mult)

    return BacktestMetrics(
        total_return_pct=total_ret.quantize(Decimal("0.01")),
        cagr_pct=Decimal(str(cagr)).quantize(Decimal("0.01")),
        sharpe=sharpe,
        max_drawdown_pct=max_dd.quantize(Decimal("0.01")),
        win_rate_pct=win_rate.quantize(Decimal("0.01")),
        avg_hold_days=avg_hold.quantize(Decimal("0.01")),
        trades=len(trades),
        multibagger_2x=_mb(Decimal("2")),
        multibagger_5x=_mb(Decimal("5")),
        multibagger_10x=_mb(Decimal("10")),
    )
