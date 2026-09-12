"""Overview KPI endpoint.

Every figure is counted from stored records. Metrics the platform cannot
compute yet are returned as `available: false` with a reason, never as zero —
"no analysis has run" and "zero vehicles were detected" are different facts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from trajyx_shared.domain import CameraStatus, RiskLevel, risk_level_from_score

from app.api.deps import SettingsDep, StoreDep, require_staff
from app.repositories.base import utc_now
from app.schemas.cameras import CameraResponse
from app.schemas.dashboard import (
    CameraSummary,
    DashboardSummary,
    EventSummary,
    Metric,
    PipelineSummary,
    RiskSummary,
)
from app.services.camera_service import CameraService
from app.services.event_service import EventService, window_start

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

RISK_ZONES = "risk_zones"
VIDEO_ANALYSIS = "video_analysis"


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Overview KPIs",
    dependencies=[Depends(require_staff)],
)
async def dashboard_summary(
    store: StoreDep,
    settings: SettingsDep,
    window_hours: Annotated[int, Query(ge=1, le=720, description="Rolling window, in hours.")] = 24,
) -> DashboardSummary:
    cameras = CameraService(store)
    events = EventService(store)

    since = window_start(days=window_hours / 24)

    status_counts = await cameras.count_by_status()
    event_counts = await events.dashboard_counts(since)
    recent = await events.recent(limit=8)

    # ---- risk zones -------------------------------------------------------
    zone_page = await store.query(RISK_ZONES)
    scores = [
        float(zone["risk_score"])
        for zone in zone_page.documents
        if isinstance(zone.get("risk_score"), int | float)
    ]

    zones_by_level: dict[RiskLevel, int] = dict.fromkeys(RiskLevel, 0)
    for score in scores:
        zones_by_level[risk_level_from_score(score)] += 1

    if scores:
        average = Metric.measured(round(sum(scores) / len(scores), 1))
        # Banded from the highest *score*, not `max()` over the levels:
        # RiskLevel is a str enum, so max() would compare alphabetically and
        # rank MODERATE above CRITICAL.
        highest_level: RiskLevel | None = risk_level_from_score(max(scores))
        high_risk = Metric.measured(
            float(zones_by_level[RiskLevel.HIGH] + zones_by_level[RiskLevel.CRITICAL])
        )
    else:
        reason = "No risk zones have been computed yet. Geospatial aggregation lands in phase 10."
        average = Metric.unavailable(reason)
        high_risk = Metric.unavailable(reason)
        highest_level = None

    # ---- pipeline totals --------------------------------------------------
    analysis_count = await store.count(VIDEO_ANALYSIS)
    if analysis_count:
        analysis_page = await store.query(VIDEO_ANALYSIS)
        vehicles = sum(
            int(document.get("vehicle_count", 0) or 0) for document in analysis_page.documents
        )
        pedestrians = sum(
            int(document.get("pedestrian_count", 0) or 0) for document in analysis_page.documents
        )
        pipeline = PipelineSummary(
            vehicles_detected=Metric.measured(float(vehicles)),
            pedestrians_detected=Metric.measured(float(pedestrians)),
            videos_analysed=Metric.measured(float(analysis_count)),
        )
    else:
        reason = "No video has been analysed yet. Detection lands in phase 4."
        pipeline = PipelineSummary(
            vehicles_detected=Metric.unavailable(reason),
            pedestrians_detected=Metric.unavailable(reason),
            videos_analysed=Metric.measured(0.0),
        )

    return DashboardSummary(
        generated_at=utc_now(),
        window_hours=window_hours,
        demo_mode=settings.demo_mode,
        cameras=CameraSummary(
            total=sum(status_counts.values()),
            online=status_counts[CameraStatus.ONLINE],
            offline=status_counts[CameraStatus.OFFLINE],
            processing=status_counts[CameraStatus.PROCESSING],
            alert=status_counts[CameraStatus.ALERT],
        ),
        events=EventSummary(
            window_hours=window_hours,
            total=event_counts["total"],
            violations=event_counts["violations"],
            behaviour=event_counts["behaviour"],
            interactions=event_counts["interactions"],
            reports=event_counts["reports"],
            near_misses=event_counts["near_misses"],
            critical=event_counts["critical"],
            demo=event_counts["demo"],
        ),
        risk=RiskSummary(
            average_risk=average,
            highest_risk_level=highest_level,
            high_risk_zones=high_risk,
            zones_by_level=zones_by_level,
        ),
        pipeline=pipeline,
        recent_events=recent,
    )


@router.get(
    "/camera-grid",
    summary="Camera monitoring grid",
    dependencies=[Depends(require_staff)],
)
async def camera_grid(store: StoreDep) -> dict[str, object]:
    """Cameras ordered for the Live Monitoring grid.

    Cameras in an alert state sort first, then by descending risk: an operator
    watching a wall display should never have to scroll to find the problem.
    """
    page = await store.query("cameras")

    def sort_key(document: dict[str, object]) -> tuple[int, float, str]:
        status = str(document.get("status", CameraStatus.OFFLINE.value))
        status_rank = 0 if status == CameraStatus.ALERT.value else 1
        score = document.get("current_risk_score")
        risk = -float(score) if isinstance(score, int | float) else 0.0
        return (status_rank, risk, str(document.get("name", "")))

    ordered = sorted(page.documents, key=sort_key)

    return {
        "items": [CameraResponse.from_document(document).model_dump(mode="json") for document in ordered],
        "total": len(ordered),
    }
