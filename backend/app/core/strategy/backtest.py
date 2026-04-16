from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.strategy.models import BacktestMetrics, BacktestResult, BacktestTrade
from app.db.models.market_data import OhlcvCandle
from app.db.models.report import Report
from app.strategies.base import Candle
from app.strategies.registry import get_strategy_class


@dataclass
class BacktestEngine:
    session: AsyncSession

    async def run(
        self,
        strategy_class: str,
        parameters: dict,
        symbols: list[str],
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        strategy_cls = get_strategy_class(strategy_class)
        strategy = strategy_cls(id="backtest", account_id="backtest", parameters=parameters)

        equity = Decimal("100000")
        equity_curve: list[dict[str, str]] = []
        trades: list[BacktestTrade] = []

        for symbol in symbols:
            candles = (
                await self.session.execute(
                    select(OhlcvCandle)
                    .where(
                        OhlcvCandle.symbol == symbol,
                        OhlcvCandle.timeframe == timeframe,
                        OhlcvCandle.ts >= start,
                        OhlcvCandle.ts <= end,
                    )
                    .order_by(OhlcvCandle.ts.asc())
                )
            ).scalars().all()
            for idx, row in enumerate(candles[:-1]):
                signal = await strategy.on_candle(
                    Candle(
                        symbol=row.symbol,
                        timeframe=row.timeframe,
                        ts=row.ts,
                        open=row.open,
                        high=row.high,
                        low=row.low,
                        close=row.close,
                        volume=row.volume,
                    ),
                    _DummyContext(),
                )
                if signal is None:
                    equity_curve.append({"ts": row.ts.isoformat(), "equity": str(equity)})
                    continue
                next_open = candles[idx + 1].open
                pnl = (candles[idx + 1].close - next_open) * signal.quantity
                if signal.side == "SELL":
                    pnl = -pnl
                equity += pnl
                trades.append(
                    BacktestTrade(
                        symbol=symbol,
                        side=signal.side,
                        quantity=signal.quantity,
                        entry_ts=candles[idx + 1].ts,
                        exit_ts=candles[idx + 1].ts,
                        entry_price=next_open,
                        exit_price=candles[idx + 1].close,
                        pnl=pnl,
                    )
                )
                equity_curve.append({"ts": candles[idx + 1].ts.isoformat(), "equity": str(equity)})

        wins = [trade for trade in trades if trade.pnl > 0]
        metrics = BacktestMetrics(
            total_return=(equity - Decimal("100000")) / Decimal("100000"),
            sharpe=Decimal("0.0"),
            sortino=Decimal("0.0"),
            calmar=Decimal("0.0"),
            max_drawdown=Decimal("0.0"),
            win_rate=(Decimal(len(wins)) / Decimal(len(trades))) if trades else Decimal("0"),
            trades=len(trades),
        )
        result = BacktestResult(metrics=metrics, equity_curve=equity_curve, trades=trades)

        report = Report(account_id=parameters.get("account_id"), report_type="backtest", artifact_path="")
        self.session.add(report)
        await self.session.flush()
        artifact = Path("reports") / "backtest" / f"{report.id}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(
            json.dumps(
                {
                    "metrics": {
                        "total_return": str(metrics.total_return),
                        "win_rate": str(metrics.win_rate),
                        "trades": metrics.trades,
                    },
                    "equity_curve": equity_curve,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report.artifact_path = str(artifact)
        report.payload_jsonb = {"metrics": {"trades": metrics.trades}}
        await self.session.commit()
        return result


class _DummyContext:
    async def place_order(self, signal):  # type: ignore[no-untyped-def]
        return ""

    async def get_position(self, symbol: str) -> Decimal:  # noqa: ARG002
        return Decimal("0")

    async def get_candles(self, symbol: str, timeframe: str, limit: int):  # noqa: ARG002
        return []
