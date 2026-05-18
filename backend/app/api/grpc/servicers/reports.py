"""gRPC ReportService servicer implementation."""

from __future__ import annotations

import uuid
from uuid import UUID

import grpc
from sqlalchemy import select

from app.api.grpc._generated.dhruva.v1 import reports_pb2, reports_pb2_grpc
from app.api.grpc.servicers._helpers import require_auth, ts_from_dt
from app.core.reports.report_service import ReportService
from app.db.models.report import Report
from app.db.session import SessionLocal
from app.infrastructure.logging import get_logger

logger = get_logger(__name__)

_REPORT_TYPE_MAP = {
    reports_pb2.ReportType.STRATEGY_PERFORMANCE: "strategy_performance",
    reports_pb2.ReportType.PORTFOLIO_MONTHLY: "portfolio_monthly",
    reports_pb2.ReportType.PORTFOLIO_QUARTERLY: "portfolio_quarterly",
    reports_pb2.ReportType.PORTFOLIO_ANNUAL: "portfolio_annual",
    reports_pb2.ReportType.RISK: "risk",
    reports_pb2.ReportType.TAX_PNL: "tax_pnl",
    reports_pb2.ReportType.TRADE_JOURNAL: "trade_journal",
    reports_pb2.ReportType.MULTI_ACCOUNT: "multi_account",
}
_REPORT_TYPE_TO_PROTO = {v: k for k, v in _REPORT_TYPE_MAP.items()}

_FORMAT_MAP = {
    reports_pb2.ReportFormat.PDF: "pdf",
    reports_pb2.ReportFormat.EXCEL: "excel",
    reports_pb2.ReportFormat.CSV: "csv",
}
_FORMAT_TO_PROTO = {v: k for k, v in _FORMAT_MAP.items()}


def _report_to_proto(report: Report) -> reports_pb2.Report:
    return reports_pb2.Report(
        id=str(report.id),
        user_id="",
        account_id=str(report.account_id),
        strategy_id=str(report.payload_jsonb.get("strategy_id", "")),
        type=_REPORT_TYPE_TO_PROTO.get(report.report_type, reports_pb2.ReportType.REPORT_TYPE_UNSPECIFIED),
        period=report.payload_jsonb.get("period", ""),
        format=_FORMAT_TO_PROTO.get(report.payload_jsonb.get("format", ""), reports_pb2.ReportFormat.REPORT_FORMAT_UNSPECIFIED),
        file_url=report.artifact_path,
        generated_at=ts_from_dt(report.created_at),
    )


class ReportServicer(reports_pb2_grpc.ReportServiceServicer):
    """Implements dhruva.v1.ReportService over gRPC."""

    async def Generate(self, request: reports_pb2.GenerateReportRequest, context: grpc.aio.ServicerContext) -> reports_pb2.Report:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                svc = ReportService(session=session)
                report_type = _REPORT_TYPE_MAP.get(request.type, "trade_journal")
                fmt = _FORMAT_MAP.get(request.format, "pdf")
                period = request.period or "1M"

                # Dispatch to the appropriate report generator
                if fmt == "excel" or report_type == "trade_journal":
                    content = await svc.trade_history_excel(request.account_id)
                    ext = "xlsx"
                else:
                    # Default: equity curve PDF for portfolio reports
                    content = await svc.equity_curve_pdf(request.account_id, period)
                    ext = "pdf"

                # Persist a Report row for audit + listing
                artifact_path = f"/reports/{request.account_id}/{report_type}_{period}.{ext}"
                report_row = Report(
                    id=uuid.uuid4(),
                    account_id=UUID(request.account_id),
                    report_type=report_type,
                    artifact_path=artifact_path,
                    payload_jsonb={
                        "period": period,
                        "format": fmt,
                        "strategy_id": request.strategy_id,
                        "size_bytes": len(content),
                    },
                )
                session.add(report_row)
                await session.commit()
                await session.refresh(report_row)
                return _report_to_proto(report_row)
            except Exception as exc:
                logger.warning("grpc.reports.generate_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def List(self, request: reports_pb2.ListReportsRequest, context: grpc.aio.ServicerContext) -> reports_pb2.ListReportsResponse:
        await require_auth(context)
        async with SessionLocal() as session:
            try:
                stmt = select(Report).order_by(Report.created_at.desc()).limit(100)
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return reports_pb2.ListReportsResponse(
                    reports=[_report_to_proto(r) for r in rows]
                )
            except Exception as exc:
                logger.warning("grpc.reports.list_failed", error=str(exc))
                await context.abort(grpc.StatusCode.INTERNAL, str(exc))
