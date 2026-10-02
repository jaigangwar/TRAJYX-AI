"""Report generation, history and export."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, StoreDep, require_operator, require_staff
from app.schemas.reports import (
    ExportFormat,
    ReportRequest,
    ReportResponse,
    ReportTypeInfo,
)
from app.services.report_service import REPORT_TYPES, ReportService, export_report

router = APIRouter(prefix="/reports", tags=["reports"])


def _service(store: StoreDep) -> ReportService:
    return ReportService(store)


ServiceDep = Annotated[ReportService, Depends(_service)]


@router.get(
    "/types",
    response_model=list[ReportTypeInfo],
    summary="Report types this build can produce",
    dependencies=[Depends(require_staff)],
)
async def report_types() -> list[ReportTypeInfo]:
    return REPORT_TYPES


@router.get(
    "",
    response_model=list[ReportResponse],
    summary="Previously generated reports",
    dependencies=[Depends(require_staff)],
)
async def list_reports(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> list[ReportResponse]:
    return await service.list_reports(limit)


@router.post(
    "",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
    dependencies=[Depends(require_operator)],
)
async def generate_report(
    payload: ReportRequest,
    service: ServiceDep,
    user: CurrentUser,
) -> ReportResponse:
    return await service.generate(payload, generated_by=user.email)


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Read a stored report",
    dependencies=[Depends(require_staff)],
)
async def get_report(report_id: str, service: ServiceDep) -> ReportResponse:
    return await service.get(report_id)


@router.get(
    "/{report_id}/export",
    summary="Download a report as CSV or JSON",
    dependencies=[Depends(require_staff)],
    response_class=Response,
)
async def export(
    report_id: str,
    service: ServiceDep,
    export_format: Annotated[ExportFormat, Query(alias="format")] = ExportFormat.CSV,
) -> Response:
    report = await service.get(report_id)
    body, media_type, filename = export_report(report, export_format)
    return Response(
        content=body,
        media_type=media_type,
        headers={
            # `attachment` so a browser saves rather than renders it, and the
            # filename carries the report type and timestamp so downloads do
            # not pile up as export(1).csv.
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
