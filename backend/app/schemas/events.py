"""The shared event model.

Every safety event in TRAJYX — a helmet violation, a hard brake, a near miss,
a driver hazard report — is the same record shape. That is what lets one table
component, one map layer, one timeline and one export path serve all of them,
and what stops "violations" and "near misses" drifting into two parallel
subsystems with different fields.

The rule: an event answers *what happened, where, when, how sure are we, and
what produced that belief*. Anything specific to one event type goes in
`details`, never as a new top-level column.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator
from trajyx_shared.domain import (
    EVENT_CATEGORY,
    DataOrigin,
    EventCategory,
    EventType,
    RiskLevel,
    Severity,
    risk_level_from_score,
)

from app.schemas.common import ApiModel, GeoPoint, ResponseModel


class EventBase(ApiModel):
    """Fields every event carries."""

    event_type: EventType
    timestamp: datetime = Field(description="When the event occurred, timezone-aware UTC.")

    camera_id: str | None = Field(
        default=None, description="Camera that observed it. Null for a driver-reported event."
    )
    road_segment_id: str | None = Field(
        default=None, description="Road segment it is attributed to, once matched."
    )
    location: GeoPoint | None = Field(
        default=None, description="Where it happened, when a geographic position is known."
    )

    severity: Severity = Severity.INFO
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Producer confidence. Null when the producer does not report one — "
            "which is different from reporting zero."
        ),
    )
    risk_score: float | None = Field(
        default=None, ge=0.0, le=100.0, description="Contribution to road risk, 0-100."
    )

    origin: DataOrigin = Field(
        default=DataOrigin.MEASURED,
        description=(
            "Provenance. DEMO and ESTIMATED are labeled in both clients; the "
            "absence of a label means the value was measured."
        ),
    )
    model_version: str | None = Field(
        default=None,
        description="Model that produced this event, so a metric stays attributable.",
    )

    track_ids: list[int] = Field(
        default_factory=list,
        description=(
            "Anonymous per-video track identifiers involved. Two or more for an "
            "interaction. Never reused across videos and never correlated "
            "between cameras."
        ),
    )

    details: dict[str, object] = Field(
        default_factory=dict,
        description=(
            "Event-type-specific payload: estimated TTC and risk factors for a "
            "near miss, measured deceleration for a hard brake, the tri-state "
            "determination for a helmet check."
        ),
    )

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        # A naive timestamp silently breaks comparison across deployments and
        # time zones, which is exactly what time-based risk depends on.
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class EventCreate(EventBase):
    """An event submitted by the analysis pipeline or a client."""

    video_analysis_id: str | None = Field(
        default=None, description="Analysis run that produced it, for pipeline events."
    )
    frame_index: int | None = Field(
        default=None, ge=0, description="Source frame, for seeking to the evidence."
    )
    evidence_key: str | None = Field(
        default=None, description="Object-storage key for the evidence frame or clip."
    )


class EventResponse(ResponseModel):
    """An event as returned by the API."""

    id: str
    event_type: EventType
    category: EventCategory = Field(description="Derived from event_type; never stored separately.")
    timestamp: datetime

    camera_id: str | None = None
    camera_name: str | None = Field(
        default=None, description="Denormalised for display, so a table needs no second request."
    )
    road_segment_id: str | None = None
    location: GeoPoint | None = None

    severity: Severity
    confidence: float | None = None
    risk_score: float | None = None
    risk_level: RiskLevel | None = Field(
        default=None, description="Band of risk_score. Null when there is no score."
    )

    origin: DataOrigin
    model_version: str | None = None
    track_ids: list[int] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)

    video_analysis_id: str | None = None
    frame_index: int | None = None
    evidence_key: str | None = None

    review_status: str | None = Field(
        default=None, description="Review workflow state, for event types that are reviewed."
    )

    @classmethod
    def from_document(cls, document: dict[str, object], camera_name: str | None = None) -> EventResponse:
        """Build a response from a stored document.

        `category` and `risk_level` are derived here rather than stored:
        duplicating them would let a stored copy disagree with the event type
        or the score it was computed from.
        """
        event_type = EventType(str(document["event_type"]))
        raw_score = document.get("risk_score")
        score = float(raw_score) if isinstance(raw_score, int | float) else None

        raw_location = document.get("location")
        location = (
            GeoPoint(
                latitude=float(raw_location["latitude"]),  # type: ignore[index]
                longitude=float(raw_location["longitude"]),  # type: ignore[index]
            )
            if isinstance(raw_location, dict)
            else None
        )

        raw_confidence = document.get("confidence")
        raw_tracks = document.get("track_ids")
        raw_details = document.get("details")

        return cls(
            id=str(document["id"]),
            event_type=event_type,
            category=EVENT_CATEGORY[event_type],
            timestamp=document["timestamp"],  # type: ignore[arg-type]
            camera_id=document.get("camera_id"),  # type: ignore[arg-type]
            camera_name=camera_name,
            road_segment_id=document.get("road_segment_id"),  # type: ignore[arg-type]
            location=location,
            severity=Severity(str(document.get("severity", Severity.INFO.value))),
            confidence=float(raw_confidence) if isinstance(raw_confidence, int | float) else None,
            risk_score=score,
            risk_level=risk_level_from_score(score) if score is not None else None,
            origin=DataOrigin(str(document.get("origin", DataOrigin.MEASURED.value))),
            model_version=document.get("model_version"),  # type: ignore[arg-type]
            track_ids=[int(value) for value in raw_tracks] if isinstance(raw_tracks, list) else [],
            details=raw_details if isinstance(raw_details, dict) else {},
            video_analysis_id=document.get("video_analysis_id"),  # type: ignore[arg-type]
            frame_index=document.get("frame_index"),  # type: ignore[arg-type]
            evidence_key=document.get("evidence_key"),  # type: ignore[arg-type]
            review_status=document.get("review_status"),  # type: ignore[arg-type]
        )
