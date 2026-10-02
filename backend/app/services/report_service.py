"""Report generation and export.

Reports are built from the same analytics aggregation the dashboard uses, so a
report and the Analytics page for the same window cannot disagree. Each run is
persisted with its parameters so a report can be re-read later exactly as it
was issued — a report that silently re-computes when reopened is not a record
of anything.

Sections that cannot be computed are kept in the report and marked
unavailable. Dropping them would leave a reader to guess whether a missing
section means "nothing happened" or "we cannot tell".
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import timedelta
from typing import Any

import structlog
from trajyx_shared.domain import DataOrigin

from app.core.errors import NotFoundError
from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.schemas.analytics import AnalyticsResponse
from app.schemas.reports import (
    ExportFormat,
    ReportColumn,
    ReportRequest,
    ReportResponse,
    ReportSection,
    ReportType,
    ReportTypeInfo,
)
from app.services.analytics_service import AnalyticsService, window_label

log = structlog.get_logger(__name__)

REPORTS = "reports"

REPORT_TYPES = [
    ReportTypeInfo(
        type=ReportType.DAILY,
        label="Daily operations",
        description="Activity, risk and review backlog for the last 24 hours.",
        default_window_hours=24,
    ),
    ReportTypeInfo(
        type=ReportType.WEEKLY,
        label="Weekly summary",
        description="Seven-day trend by day and by hour, with the week's ranked hotspots.",
        default_window_hours=168,
    ),
    ReportTypeInfo(
        type=ReportType.ROAD_SAFETY,
        label="Road safety",
        description="Per-segment risk, near misses and violations, for a traffic authority.",
        default_window_hours=720,
    ),
    ReportTypeInfo(
        type=ReportType.VIOLATION,
        label="Violation register",
        description="Every violation in the window with its camera, severity and review state.",
        default_window_hours=168,
    ),
    ReportTypeInfo(
        type=ReportType.HOTSPOT,
        label="Risk hotspots",
        description="Computed risk zones ranked by score, with the factors behind each.",
        default_window_hours=168,
    ),
]

TITLES = {info.type: info.label for info in REPORT_TYPES}


def _columns(*pairs: tuple[str, str, bool]) -> list[ReportColumn]:
    return [ReportColumn(key=key, label=label, numeric=numeric) for key, label, numeric in pairs]


class ReportService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    # ------------------------------------------------------------- generation

    async def generate(self, request: ReportRequest, *, generated_by: str) -> ReportResponse:
        now = utc_now()
        since = now - timedelta(hours=request.window_hours)

        analytics = await AnalyticsService(self._store).compute(
            request.window_hours, demo_mode=False
        )

        builders = {
            ReportType.DAILY: self._daily,
            ReportType.WEEKLY: self._weekly,
            ReportType.ROAD_SAFETY: self._road_safety,
            ReportType.VIOLATION: self._violations,
            ReportType.HOTSPOT: self._hotspots,
        }
        sections = await builders[request.type](analytics, request)

        demo = analytics.totals.demo_events
        subtitle = (
            f"{analytics.totals.events} events over {analytics.window_label}"
            + (f" — {demo} synthetic" if demo else "")
        )

        document = await self._store.create(
            REPORTS,
            {
                "type": request.type.value,
                "title": TITLES[request.type],
                "subtitle": subtitle,
                "generated_at": now,
                "generated_by": generated_by,
                "window_hours": request.window_hours,
                "window_label": analytics.window_label,
                "period_start": since,
                "period_end": now,
                "parameters": request.model_dump(mode="json"),
                "record_count": analytics.totals.events,
                "demo_record_count": demo,
                "sections": [section.model_dump(mode="json") for section in sections],
                "created_at": now,
            },
        )
        log.info(
            "report.generated",
            report_type=request.type.value,
            window_hours=request.window_hours,
            records=analytics.totals.events,
            by=generated_by,
        )
        return ReportResponse.model_validate(document)

    async def list_reports(self, limit: int = 30) -> list[ReportResponse]:
        page = await self._store.query(
            REPORTS, Query().order_by("generated_at", descending=True).take(limit)
        )
        return [ReportResponse.model_validate(document) for document in page.documents]

    async def get(self, report_id: str) -> ReportResponse:
        document = await self._store.get(REPORTS, report_id)
        if document is None:
            raise NotFoundError(
                f"Report {report_id} not found.", details={"report_id": report_id}
            )
        return ReportResponse.model_validate(document)

    # ---------------------------------------------------------------- builders

    async def _daily(
        self, analytics: AnalyticsResponse, request: ReportRequest
    ) -> list[ReportSection]:
        return [
            self._totals_section(analytics),
            ReportSection(
                title="Activity by hour",
                note="Events, near misses and mean risk per hour of the day. Mean risk is blank "
                "for an hour in which no event carried a score.",
                columns=_columns(
                    ("label", "Hour", False),
                    ("events", "Events", True),
                    ("near_misses", "Near misses", True),
                    ("violations", "Violations", True),
                    ("mean_risk", "Mean risk", True),
                ),
                rows=[
                    bucket.model_dump(mode="json")
                    for bucket in analytics.by_hour
                    if bucket.events
                ],
            ),
            self._breakdown_section(
                "Events by type", analytics.by_event_type, "Event type"
            ),
            await self._review_backlog(),
        ]

    async def _weekly(
        self, analytics: AnalyticsResponse, request: ReportRequest
    ) -> list[ReportSection]:
        return [
            self._totals_section(analytics),
            ReportSection(
                title="Daily trend",
                note="One row per day in the window, including days with no activity.",
                columns=_columns(
                    ("label", "Day", False),
                    ("events", "Events", True),
                    ("near_misses", "Near misses", True),
                    ("violations", "Violations", True),
                    ("mean_risk", "Mean risk", True),
                ),
                rows=[bucket.model_dump(mode="json") for bucket in analytics.by_day],
            ),
            ReportSection(
                title="Activity by weekday",
                columns=_columns(
                    ("label", "Weekday", False),
                    ("events", "Events", True),
                    ("near_misses", "Near misses", True),
                    ("mean_risk", "Mean risk", True),
                ),
                rows=[bucket.model_dump(mode="json") for bucket in analytics.by_weekday],
            ),
            self._segments_section(analytics),
        ]

    async def _road_safety(
        self, analytics: AnalyticsResponse, request: ReportRequest
    ) -> list[ReportSection]:
        return [
            self._totals_section(analytics),
            self._segments_section(analytics),
            self._breakdown_section(
                "Traffic composition", analytics.traffic_composition, "Vehicle class"
            ),
            self._coverage_section(analytics),
        ]

    async def _violations(
        self, analytics: AnalyticsResponse, request: ReportRequest
    ) -> list[ReportSection]:
        since = analytics.generated_at - timedelta(hours=analytics.window_hours)
        query = (
            Query()
            .where(Filter.gte("timestamp", since))
            .where(Filter.eq("category", "VIOLATION"))
            .order_by("timestamp", descending=True)
            .take(500)
        )
        if request.road_segment_id:
            query = query.where(Filter.eq("road_segment_id", request.road_segment_id))

        page = await self._store.query("risk_events", query)
        cameras = await self._camera_names()

        rows = [
            {
                "timestamp": document["timestamp"].isoformat()
                if hasattr(document.get("timestamp"), "isoformat")
                else str(document.get("timestamp")),
                "event_type": str(document.get("event_type", "")),
                "camera": cameras.get(str(document.get("camera_id")), "—"),
                "severity": str(document.get("severity", "")),
                "confidence": document.get("confidence"),
                "risk_score": document.get("risk_score"),
                "review_status": str(document.get("review_status") or "—"),
                "origin": str(document.get("origin", "")),
            }
            for document in page.documents
        ]

        section = ReportSection(
            title="Violation register",
            note="Capped at 500 rows, newest first. `origin` distinguishes measured records "
            "from synthetic demo data.",
            columns=_columns(
                ("timestamp", "Time", False),
                ("event_type", "Violation", False),
                ("camera", "Camera", False),
                ("severity", "Severity", False),
                ("confidence", "Confidence", True),
                ("risk_score", "Risk", True),
                ("review_status", "Review", False),
                ("origin", "Origin", False),
            ),
            rows=rows,
        )
        if not rows:
            section.available = False
            section.unavailable_reason = (
                f"No violations are stored in the last {analytics.window_label}."
            )

        return [self._totals_section(analytics), section, await self._review_backlog()]

    async def _hotspots(
        self, analytics: AnalyticsResponse, request: ReportRequest
    ) -> list[ReportSection]:
        page = await self._store.query(
            "risk_zones", Query().order_by("risk_score", descending=True).take(100)
        )
        rows = [
            {
                "road_name": str(document.get("road_name") or "Unnamed"),
                "risk_score": document.get("risk_score"),
                "risk_level": str(document.get("risk_level", "")),
                "confidence": document.get("confidence"),
                "radius_m": document.get("radius_m"),
                "event_count": document.get("event_count"),
                "near_miss_count": document.get("near_miss_count"),
                "peak_hour": document.get("peak_hour"),
                "factors": ", ".join(
                    str(factor) for factor in (document.get("top_risk_factors") or [])
                ),
                "origin": str(document.get("origin", "")),
            }
            for document in page.documents
        ]

        section = ReportSection(
            title="Risk zones",
            note="Zones are computed from attributed events, never placed by hand. The factors "
            "column lists what drove each score.",
            columns=_columns(
                ("road_name", "Road", False),
                ("risk_score", "Score", True),
                ("risk_level", "Level", False),
                ("confidence", "Confidence", True),
                ("radius_m", "Radius (m)", True),
                ("event_count", "Events", True),
                ("near_miss_count", "Near misses", True),
                ("peak_hour", "Peak hour", True),
                ("factors", "Top factors", False),
                ("origin", "Origin", False),
            ),
            rows=rows,
        )
        if not rows:
            section.available = False
            section.unavailable_reason = (
                "No risk zones have been computed. Run the geospatial aggregator from the "
                "Risk Map page."
            )

        return [self._totals_section(analytics), section, self._segments_section(analytics)]

    # --------------------------------------------------------- shared sections

    def _totals_section(self, analytics: AnalyticsResponse) -> ReportSection:
        totals = analytics.totals
        mean = totals.mean_risk
        return ReportSection(
            title="Summary",
            note=f"Counted from stored records over {analytics.window_label}.",
            columns=_columns(("metric", "Metric", False), ("value", "Value", False)),
            rows=[
                {"metric": "Events", "value": totals.events},
                {"metric": "Violations", "value": totals.violations},
                {"metric": "Near misses", "value": totals.near_misses},
                {"metric": "Risky behaviour", "value": totals.behaviour},
                {"metric": "Driver reports", "value": totals.reports},
                {"metric": "Critical-scored events", "value": totals.critical},
                {
                    "metric": "Mean risk score",
                    # An unavailable metric renders as a stated reason, not 0.
                    "value": mean.value if mean.available else "UNABLE TO DETERMINE",
                },
                {"metric": "Synthetic (demo) records", "value": totals.demo_events},
            ],
        )

    def _segments_section(self, analytics: AnalyticsResponse) -> ReportSection:
        section = ReportSection(
            title="Road segments by risk",
            note="Risk score comes from the geospatial aggregator's own window; event counts "
            "come from this report's window. They are reported side by side, not merged.",
            columns=_columns(
                ("name", "Segment", False),
                ("road_name", "Road", False),
                ("risk_score", "Risk", True),
                ("risk_level", "Level", False),
                ("events", "Events", True),
                ("near_misses", "Near misses", True),
                ("violations", "Violations", True),
                ("peak_hour", "Peak hour", True),
            ),
            rows=[row.model_dump(mode="json") for row in analytics.top_segments],
        )
        if not section.rows:
            section.available = False
            section.unavailable_reason = (
                "No road segment has a risk score or any events in this window."
            )
        return section

    def _breakdown_section(self, title: str, breakdown: Any, label: str) -> ReportSection:
        return ReportSection(
            title=title,
            columns=_columns(
                ("label", label, False), ("count", "Count", True), ("share", "Share", True)
            ),
            rows=[item.model_dump(mode="json") for item in breakdown.slices],
            available=breakdown.available,
            unavailable_reason=breakdown.unavailable_reason,
        )

    def _coverage_section(self, analytics: AnalyticsResponse) -> ReportSection:
        section = ReportSection(
            title="Detector coverage",
            note="Which safety checks the analysed cameras could actually run. A check with no "
            "supporting camera reports nothing — that is a coverage gap, not a clean road.",
            columns=_columns(
                ("label", "Check", False),
                ("analyses_supported", "Runs supported", True),
                ("analyses_total", "Runs total", True),
                ("reason", "Why unavailable", False),
            ),
            rows=[
                {
                    "label": row.label,
                    "analyses_supported": row.analyses_supported,
                    "analyses_total": row.analyses_total,
                    "reason": row.reasons[0] if row.reasons else "—",
                }
                for row in analytics.detector_coverage
            ],
        )
        if not section.rows:
            section.available = False
            section.unavailable_reason = (
                "No video has been analysed in this window, so detector capability is unknown."
            )
        return section

    async def _review_backlog(self) -> ReportSection:
        page = await self._store.query(
            "risk_events", Query().where(Filter.eq("review_status", "PENDING")).take(1000)
        )
        counts: Counter[str] = Counter(
            str(document.get("event_type", "")) for document in page.documents
        )
        section = ReportSection(
            title="Review backlog",
            note="Events awaiting operator review, across all time rather than the report "
            "window — a backlog does not expire when the window moves.",
            columns=_columns(("event_type", "Event type", False), ("pending", "Pending", True)),
            rows=[
                {"event_type": key.replace("_", " ").capitalize(), "pending": value}
                for key, value in counts.most_common()
            ],
        )
        if not section.rows:
            section.available = False
            section.unavailable_reason = "Nothing is awaiting review."
        return section

    async def _camera_names(self) -> dict[str, str]:
        page = await self._store.query("cameras")
        return {str(camera["id"]): str(camera.get("name", "")) for camera in page.documents}


def export_report(report: ReportResponse, export_format: ExportFormat) -> tuple[str, str, str]:
    """Render a report for download.

    Returns `(body, media_type, filename)`.

    CSV carries the header block and every section in sequence, with the
    section title and any unavailability reason as comment rows. A spreadsheet
    of numbers whose provenance has been stripped is how an estimate becomes
    mistaken for a measurement.
    """
    stamp = report.generated_at.strftime("%Y%m%d-%H%M")
    slug = f"trajyx-{report.type.value.lower().replace('_', '-')}-{stamp}"

    if export_format is ExportFormat.JSON:
        return report.model_dump_json(indent=2), "application/json", f"{slug}.json"

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")

    writer.writerow(["TRAJYX", report.title])
    writer.writerow(["Generated", report.generated_at.isoformat()])
    writer.writerow(["Generated by", report.generated_by])
    writer.writerow(["Window", report.window_label])
    writer.writerow(["Period", f"{report.period_start.isoformat()} to {report.period_end.isoformat()}"])
    writer.writerow(["Records", report.record_count])
    writer.writerow(["Synthetic records", report.demo_record_count])
    if report.demo_record_count:
        writer.writerow(
            [
                "NOTE",
                f"{report.demo_record_count} of {report.record_count} records are synthetic "
                "demo data. This report is not operational.",
            ]
        )
    writer.writerow([])

    for section in report.sections:
        writer.writerow([f"# {section.title}"])
        if section.note:
            writer.writerow([f"# {section.note}"])
        if not section.available:
            writer.writerow([f"# UNABLE TO DETERMINE: {section.unavailable_reason}"])
            writer.writerow([])
            continue

        writer.writerow([column.label for column in section.columns])
        for row in section.rows:
            writer.writerow(
                [
                    # An absent value stays blank rather than becoming 0: the
                    # distinction survives into the spreadsheet.
                    "" if row.get(column.key) is None else row.get(column.key)
                    for column in section.columns
                ]
            )
        writer.writerow([])

    return buffer.getvalue(), "text/csv", f"{slug}.csv"


def demo_note(origin: str) -> str | None:
    """A banner line when a record set is synthetic."""
    return "Synthetic demo data." if origin == DataOrigin.DEMO.value else None


__all__ = [
    "REPORT_TYPES",
    "ReportService",
    "demo_note",
    "export_report",
    "window_label",
]
