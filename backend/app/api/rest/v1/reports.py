"""Reports REST endpoints — download equity-curve PDF, trade history Excel,
and portfolio snapshot PDF for a given account.

All endpoints are authenticated (JWT required) and scoped to the requesting
user's account.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.dependencies import get_current_user
from app.core.reports.report_service import ReportService
from app.db.models.user import User
from app.db.session import get_session

router = APIRouter()


def _get_report_service(session: AsyncSession = Depends(get_session)) -> ReportService:
    return ReportService(session=session)


@router.get(
    "/accounts/{account_id}/reports/equity-curve.pdf",
    tags=["reports"],
    summary="Download equity curve PDF",
    response_class=Response,
)
async def download_equity_curve_pdf(
    account_id: UUID,
    period: str = Query(default="all", description="Human-readable period label, e.g. '2025-01 – 2025-12'"),
    _user: User = Depends(get_current_user),
    service: ReportService = Depends(_get_report_service),
) -> Response:
    content = await service.equity_curve_pdf(str(account_id), period)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=equity_curve.pdf"},
    )


@router.get(
    "/accounts/{account_id}/reports/trades.xlsx",
    tags=["reports"],
    summary="Download trade history Excel workbook",
    response_class=Response,
)
async def download_trades_excel(
    account_id: UUID,
    _user: User = Depends(get_current_user),
    service: ReportService = Depends(_get_report_service),
) -> Response:
    content = await service.trade_history_excel(str(account_id))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=trades.xlsx"},
    )


@router.get(
    "/accounts/{account_id}/reports/snapshot.pdf",
    tags=["reports"],
    summary="Download portfolio snapshot PDF",
    response_class=Response,
)
async def download_portfolio_snapshot(
    account_id: UUID,
    _user: User = Depends(get_current_user),
    service: ReportService = Depends(_get_report_service),
) -> Response:
    content = await service.portfolio_snapshot_pdf(str(account_id))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=portfolio_snapshot.pdf"},
    )
