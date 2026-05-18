"""gRPC PortfolioService servicer implementation."""

from __future__ import annotations

import math
from decimal import Decimal
from uuid import UUID

import grpc
from sqlalchemy import select

from app.api.grpc._generated.dhruva.v1 import common_pb2, portfolio_pb2, portfolio_pb2_grpc
from app.api.grpc.servicers._helpers import require_auth, ts_from_dt
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_EXCHANGE_TO_PROTO = {
    "NSE": common_pb2.Exchange.NSE,
    "BSE": common_pb2.Exchange.BSE,
    "NFO": common_pb2.Exchange.NFO,
    "MCX": common_pb2.Exchange.MCX,
}


def _pos_to_proto(pos: Position) -> portfolio_pb2.Position:
    exchange_val = pos.exchange.value if hasattr(pos.exchange, "value") else str(pos.exchange)
    qty = pos.quantity or Decimal("0")
    avg = pos.avg_cost or Decimal("0")
    # current_price not stored; use avg_cost as fallback
    current_price = avg
    market_value = qty * current_price
    unrealized_pnl = (current_price - avg) * qty
    return portfolio_pb2.Position(
        account_id=str(pos.account_id),
        symbol=pos.symbol,
        exchange=_EXCHANGE_TO_PROTO.get(exchange_val, common_pb2.Exchange.EXCHANGE_UNSPECIFIED),
        quantity=str(qty),
        avg_cost=str(avg),
        current_price=str(current_price),
        market_value=str(market_value),
        unrealized_pnl=str(unrealized_pnl),
        realized_pnl=str(pos.realized_pnl or Decimal("0")),
        sector="",
        instrument_type="EQ",
        updated_at=ts_from_dt(pos.updated_at),
    )


def _compute_analytics(orders: list[Order]) -> portfolio_pb2.Analytics:
    """Compute portfolio analytics from order history using daily P&L."""
    filled = [o for o in orders if str(getattr(o.status, "value", o.status)).lower() == "filled"]
    if not filled:
        return portfolio_pb2.Analytics(
            sharpe="0", sortino="0", calmar="0", max_drawdown="0",
            var_95="0", cumulative_return="0", volatility="0",
            trade_count=0, win_rate=0.0,
        )

    # P&L per trade (simplified: filled_quantity * price, sign from side)
    pnls: list[float] = []
    wins = 0
    for order in filled:
        side_val = str(getattr(order.side, "value", order.side)).upper()
        price = float(order.price or 0)
        qty = float(order.quantity or 0)
        pnl = price * qty * (1 if side_val == "BUY" else -1)
        pnls.append(pnl)
        if pnl > 0:
            wins += 1

    n = len(pnls)
    mean_pnl = sum(pnls) / n
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / max(n - 1, 1)
    std = math.sqrt(variance) if variance > 0 else 1e-9

    cumulative = sum(pnls)
    sharpe = (mean_pnl / std) * math.sqrt(252) if std > 0 else 0.0

    # Downside deviation for Sortino
    downside_sq = sum((p - mean_pnl) ** 2 for p in pnls if p < mean_pnl) / max(n - 1, 1)
    sortino_std = math.sqrt(downside_sq) if downside_sq > 0 else 1e-9
    sortino = (mean_pnl / sortino_std) * math.sqrt(252)

    # Max drawdown via running peak
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = (peak - running) / max(abs(peak), 1e-9)
        if dd > max_dd:
            max_dd = dd

    calmar = (cumulative / max(abs(max_dd * peak), 1e-9)) if max_dd > 0 else 0.0

    # VaR 95%: 5th percentile of pnls
    sorted_pnls = sorted(pnls)
    var_95_idx = max(int(n * 0.05) - 1, 0)
    var_95 = abs(sorted_pnls[var_95_idx])

    win_rate = wins / n if n > 0 else 0.0

    return portfolio_pb2.Analytics(
        sharpe=f"{sharpe:.4f}",
        sortino=f"{sortino:.4f}",
        calmar=f"{calmar:.4f}",
        max_drawdown=f"{max_dd:.4f}",
        var_95=f"{var_95:.2f}",
        cumulative_return=f"{cumulative:.2f}",
        volatility=f"{std:.4f}",
        trade_count=n,
        win_rate=win_rate,
    )


class PortfolioServicer(portfolio_pb2_grpc.PortfolioServiceServicer):
    """Implements dhruva.v1.PortfolioService over gRPC."""

    async def GetPositions(self, request: portfolio_pb2.GetPositionsRequest, context: grpc.aio.ServicerContext) -> portfolio_pb2.GetPositionsResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(Position).where(
                    Position.account_id == UUID(request.account_id),
                    Position.quantity != 0,
                )
                result = await session.execute(stmt)
                positions = result.scalars().all()
                return portfolio_pb2.GetPositionsResponse(
                    positions=[_pos_to_proto(p) for p in positions]
                )
            except Exception as exc:
                logger.warning("grpc.portfolio.positions_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def GetEquityCurve(self, request: portfolio_pb2.GetEquityCurveRequest, context: grpc.aio.ServicerContext) -> portfolio_pb2.GetEquityCurveResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(Order).order_by(Order.created_at.asc())
                if request.account_id:
                    stmt = stmt.where(Order.account_id == UUID(request.account_id))
                result = await session.execute(stmt)
                orders = result.scalars().all()

                # Build a daily equity curve from filled orders
                from collections import defaultdict
                daily: dict = defaultdict(float)
                for o in orders:
                    if str(getattr(o.status, "value", o.status)).lower() == "filled":
                        day = o.created_at.date().isoformat() if o.created_at else "unknown"
                        side_val = str(getattr(o.side, "value", o.side)).upper()
                        pnl = float(o.price or 0) * float(o.quantity or 0) * (1 if side_val == "BUY" else -1)
                        daily[day] += pnl

                points: list[portfolio_pb2.EquityPoint] = []
                running = 0.0
                prev = 0.0
                for day_str in sorted(daily):
                    running += daily[day_str]
                    daily_ret = (running - prev) / max(abs(prev), 1e-9) if prev != 0 else 0.0
                    from datetime import datetime
                    dt = datetime.fromisoformat(day_str)
                    ts = ts_from_dt(dt)
                    points.append(portfolio_pb2.EquityPoint(
                        ts=ts,
                        equity=f"{running:.2f}",
                        daily_return=f"{daily_ret:.4f}",
                    ))
                    prev = running

                return portfolio_pb2.GetEquityCurveResponse(points=points)
            except Exception as exc:
                logger.warning("grpc.portfolio.equity_curve_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def GetAnalytics(self, request: portfolio_pb2.GetAnalyticsRequest, context: grpc.aio.ServicerContext) -> portfolio_pb2.Analytics:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(Order)
                if request.account_id:
                    stmt = stmt.where(Order.account_id == UUID(request.account_id))
                result = await session.execute(stmt)
                orders = result.scalars().all()
                return _compute_analytics(list(orders))
            except Exception as exc:
                logger.warning("grpc.portfolio.analytics_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))
