"""Analytics response schemas.

Every number here is counted from stored records inside the requested window.
Nothing is modelled, smoothed or extrapolated, and a bucket with no scored
event reports `mean_risk: null` rather than 0 — an hour in which nothing was
detected and an hour in which everything scored zero are different facts.

Where a figure genuinely cannot be derived from what the platform has
measured, it is returned as an unavailable `Metric` carrying the reason,
rather than being approximated. `helmet_compliance_rate` is the standing
example: the violation count is known, the rider population is not, so a rate
would be an invention.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import ResponseModel
from app.schemas.dashboard import Metric


class Bucket(ResponseModel):
    """One time bucket of activity."""

    key: str = Field(description="Stable identifier: hour '00'-'23', weekday '0'-'6', or ISO date.")
    label: str = Field(description="Display label, already localised for the dashboard.")
    events: int
    near_misses: int
    violations: int
    mean_risk: float | None = Field(
        default=None,
        description="Mean risk score of the *scored* events in this bucket, or null when none carried a score.",
    )
    scored_events: int = Field(
        default=0, description="How many events carried a risk score, so mean_risk is auditable."
    )


class Slice(ResponseModel):
    """One category of a breakdown, with its share of the whole."""

    key: str
    label: str
    count: int
    share: float = Field(ge=0.0, le=1.0, description="Fraction of the breakdown total.")


class Breakdown(ResponseModel):
    """A categorical breakdown that may not be computable at all."""

    slices: list[Slice] = Field(default_factory=list)
    total: int = 0
    available: bool
    unavailable_reason: str | None = None


class CoverageRow(ResponseModel):
    """Whether a safety check can run, across the analyses in the window.

    Detector capability is a property of camera geometry, not of the model, so
    this is the honest answer to "why does this road report no red-light
    violations" — usually because no signal phase is wired to that camera.
    """

    check: str
    label: str
    analyses_supported: int
    analyses_total: int
    reasons: list[str] = Field(
        default_factory=list, description="Distinct reasons the check was unavailable."
    )


class SegmentRow(ResponseModel):
    """A road segment ranked by risk, for the analytics leaderboard."""

    id: str
    name: str
    road_name: str | None = None
    risk_score: float | None = None
    risk_level: str | None = None
    events: int
    near_misses: int
    violations: int
    peak_hour: int | None = None


class AnalyticsTotals(ResponseModel):
    events: int
    violations: int
    behaviour: int
    interactions: int
    reports: int
    near_misses: int
    critical: int
    scored_events: int
    mean_risk: Metric
    demo_events: int = Field(
        description="How many of the above are synthetic, so the total is auditable."
    )


class AnalyticsResponse(ResponseModel):
    generated_at: datetime
    window_hours: int
    window_label: str
    demo_mode: bool

    totals: AnalyticsTotals

    by_hour: list[Bucket] = Field(description="Always 24 buckets, including empty ones.")
    by_weekday: list[Bucket] = Field(description="Always 7 buckets, Monday first.")
    by_day: list[Bucket] = Field(description="One per day in the window, oldest first.")

    by_event_type: Breakdown
    by_category: Breakdown
    by_severity: Breakdown
    by_origin: Breakdown
    traffic_composition: Breakdown

    peak_hour: Metric
    peak_hour_events: Metric
    helmet_violations: Metric
    helmet_compliance_rate: Metric
    mean_inference_ms: Metric

    detector_coverage: list[CoverageRow] = Field(default_factory=list)
    top_segments: list[SegmentRow] = Field(default_factory=list)
