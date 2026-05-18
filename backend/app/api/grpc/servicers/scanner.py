"""gRPC ScannerService servicer implementation."""

from __future__ import annotations

import grpc
from sqlalchemy import select

from app.api.grpc._generated.dhruva.v1 import common_pb2, scanner_pb2, scanner_pb2_grpc
from app.api.grpc.servicers._helpers import require_auth, ts_from_dt
from app.db.models.scanner import ScanResult as ScanResultModel
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_PATTERN_TO_PROTO = {
    "momentum": scanner_pb2.Pattern.MOMENTUM,
    "mean_reversion": scanner_pb2.Pattern.MEAN_REVERSION,
    "breakout": scanner_pb2.Pattern.BREAKOUT,
    "reversal": scanner_pb2.Pattern.REVERSAL,
}
_PROTO_TO_PATTERN = {v: k for k, v in _PATTERN_TO_PROTO.items()}

_EXCHANGE_TO_PROTO = {
    "NSE": common_pb2.Exchange.NSE,
    "BSE": common_pb2.Exchange.BSE,
    "NFO": common_pb2.Exchange.NFO,
    "MCX": common_pb2.Exchange.MCX,
}


def _result_to_proto(row: ScanResultModel) -> scanner_pb2.ScanResult:
    pattern_val = str(getattr(row, "pattern", "")).lower()
    exchange_val = str(getattr(row, "exchange", "NSE")).upper()
    return scanner_pb2.ScanResult(
        symbol=row.symbol,
        exchange=_EXCHANGE_TO_PROTO.get(exchange_val, common_pb2.Exchange.NSE),
        pattern=_PATTERN_TO_PROTO.get(pattern_val, scanner_pb2.Pattern.PATTERN_UNSPECIFIED),
        setup_score=float(getattr(row, "setup_score", 0) or 0),
        reason=getattr(row, "reason", "") or "",
        last_price=str(getattr(row, "last_price", "0") or "0"),
        change_pct=str(getattr(row, "change_pct", "0") or "0"),
        detected_at=ts_from_dt(getattr(row, "detected_at", None) or getattr(row, "created_at", None)),
    )


class ScannerServicer(scanner_pb2_grpc.ScannerServiceServicer):
    """Implements dhruva.v1.ScannerService over gRPC."""

    async def Run(self, request: scanner_pb2.RunScanRequest, context: grpc.aio.ServicerContext) -> scanner_pb2.RunScanResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(ScanResultModel).order_by(
                    ScanResultModel.setup_score.desc()
                )

                # Filter by pattern if specified
                if request.patterns:
                    pattern_strs = [
                        _PROTO_TO_PATTERN[p]
                        for p in request.patterns
                        if p in _PROTO_TO_PATTERN
                    ]
                    if pattern_strs:
                        stmt = stmt.where(ScanResultModel.pattern.in_(pattern_strs))

                # Filter by min_score
                if request.min_score > 0:
                    stmt = stmt.where(ScanResultModel.setup_score >= request.min_score)

                # Limit results
                limit = request.limit if request.limit > 0 else 50
                stmt = stmt.limit(limit)

                result = await session.execute(stmt)
                rows = result.scalars().all()

                return scanner_pb2.RunScanResponse(
                    results=[_result_to_proto(r) for r in rows]
                )
            except Exception as exc:
                logger.warning("grpc.scanner.run_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))
