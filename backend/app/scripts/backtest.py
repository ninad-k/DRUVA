from __future__ import annotations

import argparse
from datetime import datetime

import asyncio

from app.core.strategy.backtest import BacktestEngine
from app.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    async with SessionLocal() as session:
        engine = BacktestEngine(session=session)
        result = await engine.run(
            strategy_class=args.strategy,
            parameters={},
            symbols=[args.symbol],
            timeframe=args.timeframe,
            start=datetime.fromisoformat(args.start),
            end=datetime.fromisoformat(args.end),
        )
        print(result.metrics)


if __name__ == "__main__":
    asyncio.run(_run())
