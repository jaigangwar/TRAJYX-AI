"""Overview KPI schemas.

Every figure here is either counted from stored records or explicitly null.
There is no code path that writes a KPI from a literal, and a metric that
cannot be computed yet is reported as `null` with `available: false` rather
than as zero — "no cameras have run yet" and "zero vehicles were detected" are
different facts, and a dashboard that conflates them is lying.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field
from trajyx_shared.domain import RiskLevel

from app.schemas.common import ResponseModel
from app.schemas.events import EventResponse


class Metric(ResponseModel):
    """One KPI, with honest availability."""

    value: float | None = Field(description="The measured value, or null when not yet computable.")
    available: bool = Field(
        description=(
            "False when nothing has produced this metric yet. The UI shows a dash "
            "rather than a zero, because no data and a genuine zero are different."
        )
    )
    unavailable_reason: str | None = Field(
        default=None, description="Why it is unavailable, shown as a tooltip."
    )
    unit: str | None = None

    @classmethod
    def measured(cls, value: float, unit: str | None = None) -> Metric:
        return cls(value=value, available=True, unit=unit)

    @classmethod
    def unavailable(cls, reason: str, unit: str | None = None) -> Metric:
        return cls(value=None, available=False, unavailable_reason=reason, unit=unit)


class CameraSummary(ResponseModel):
    total: int
    online: int
    offline: int
    processing: int
    alert: int


class EventSummary(ResponseModel):
    """Counts over the requested window."""

    window_hours: int
    total: int
    violations: int
    behaviour: int
    interactions: int
    reports: int
    near_misses: int
    critical: int
    demo: int = Field(
        description="How many of the above are synthetic demo records, so the total is auditable."
    )


class RiskSummary(ResponseModel):
    average_risk: Metric
    highest_risk_level: RiskLevel | None = Field(
        default=None, description="Worst level currently present. Null when nothing is scored."
    )
    high_risk_zones: Metric
    zones_by_level: dict[RiskLevel, int] = Field(default_factory=dict)


class PipelineSummary(ResponseModel):
    """Detection totals. Unavailable until the pipeline exists (phases 4-5)."""

    vehicles_detected: Metric
    pedestrians_detected: Metric
    videos_analysed: Metric


class DashboardSummary(ResponseModel):
    generated_at: datetime
    window_hours: int
    demo_mode: bool = Field(description="Whether this deployment is generating demo records.")

    cameras: CameraSummary
    events: EventSummary
    risk: RiskSummary
    pipeline: PipelineSummary
    recent_events: list[EventResponse] = Field(default_factory=list)
