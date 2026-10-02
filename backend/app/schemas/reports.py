"""Report schemas.

A report is a list of sections, each a titled table. Keeping the shape generic
means the web table, the CSV writer and the JSON export are one implementation
rather than three, and a new report type adds a builder rather than a new
endpoint, schema and exporter.

Every report records the window it covers, the parameters it was run with, and
how many of its records are synthetic, so a report can be audited after the
fact rather than taken on trust.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from app.schemas.common import ResponseModel


class ReportType(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    ROAD_SAFETY = "ROAD_SAFETY"
    VIOLATION = "VIOLATION"
    HOTSPOT = "HOTSPOT"


class ExportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class ReportColumn(ResponseModel):
    key: str
    label: str
    numeric: bool = Field(
        default=False, description="Right-align and format as a number in the UI and CSV."
    )


class ReportSection(ResponseModel):
    """One titled table inside a report."""

    title: str
    note: str | None = Field(
        default=None, description="What the section measures, and any caveat that applies to it."
    )
    columns: list[ReportColumn] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    available: bool = Field(
        default=True,
        description="False when the section could not be computed. `unavailable_reason` says why.",
    )
    unavailable_reason: str | None = None


class ReportTypeInfo(ResponseModel):
    """A report the platform can produce."""

    type: ReportType
    label: str
    description: str
    default_window_hours: int


class ReportRequest(ResponseModel):
    type: ReportType
    window_hours: int = Field(
        default=24, ge=1, le=2160, description="Rolling window the report covers."
    )
    road_segment_id: str | None = Field(
        default=None, description="Restrict to one road segment, where the report supports it."
    )


class ReportResponse(ResponseModel):
    id: str
    type: ReportType
    title: str
    subtitle: str
    generated_at: datetime
    generated_by: str = Field(description="Email of the user who ran it.")
    window_hours: int
    window_label: str
    period_start: datetime
    period_end: datetime
    parameters: dict[str, Any] = Field(default_factory=dict)

    record_count: int = Field(description="Events the report is built from.")
    demo_record_count: int = Field(
        description="How many of those are synthetic. Non-zero means the report is not operational."
    )
    sections: list[ReportSection] = Field(default_factory=list)
