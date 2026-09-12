"""Road segment, risk zone and driver alert schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator
from trajyx_shared.domain import AlertLevel, EventType, RiskLevel, risk_level_from_score

from app.schemas.common import ApiModel, GeoPoint, ResponseModel


class RoadSegmentBase(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    road_name: str | None = Field(default=None, max_length=160)
    path: list[GeoPoint] = Field(
        min_length=2, description="Polyline of the segment, in travel order."
    )
    speed_limit_kmh: float | None = Field(default=None, gt=0, le=200)
    lanes: int | None = Field(default=None, ge=1, le=12)
    one_way: bool = False

    @field_validator("path")
    @classmethod
    def _reject_duplicate_points(cls, path: list[GeoPoint]) -> list[GeoPoint]:
        if len({(point.latitude, point.longitude) for point in path}) < 2:
            raise ValueError("path must contain at least two distinct points")
        return path


class RoadSegmentCreate(RoadSegmentBase):
    pass


class RoadSegmentUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    road_name: str | None = Field(default=None, max_length=160)
    path: list[GeoPoint] | None = Field(default=None, min_length=2)
    speed_limit_kmh: float | None = Field(default=None, gt=0, le=200)
    lanes: int | None = Field(default=None, ge=1, le=12)
    one_way: bool | None = None


class RoadSegmentResponse(ResponseModel):
    id: str
    name: str
    road_name: str | None = None
    path: list[GeoPoint]
    length_m: float
    bearing_deg: float | None = Field(
        default=None, description="Overall direction of travel, clockwise from true north."
    )
    speed_limit_kmh: float | None = None
    lanes: int | None = None
    one_way: bool = False

    risk_score: float | None = Field(
        default=None, description="Aggregate risk. Null until events have been attributed here."
    )
    risk_level: RiskLevel | None = None
    risk_confidence: float | None = None
    event_count: int = 0
    near_miss_count: int = 0
    violation_count: int = 0
    top_risk_factors: list[str] = Field(default_factory=list)
    peak_hour: int | None = Field(
        default=None, description="Hour of day with the highest observed risk, 0-23."
    )
    last_event_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_document(cls, document: dict) -> RoadSegmentResponse:
        raw_path = document.get("path") or []
        path = [
            GeoPoint(latitude=float(point["latitude"]), longitude=float(point["longitude"]))
            for point in raw_path
            if isinstance(point, dict)
        ]
        raw_score = document.get("risk_score")
        score = float(raw_score) if isinstance(raw_score, int | float) else None

        return cls(
            id=str(document["id"]),
            name=str(document.get("name", "")),
            road_name=document.get("road_name"),
            path=path,
            length_m=float(document.get("length_m", 0.0) or 0.0),
            bearing_deg=document.get("bearing_deg"),
            speed_limit_kmh=document.get("speed_limit_kmh"),
            lanes=document.get("lanes"),
            one_way=bool(document.get("one_way", False)),
            risk_score=score,
            risk_level=risk_level_from_score(score) if score is not None else None,
            risk_confidence=document.get("risk_confidence"),
            event_count=int(document.get("event_count", 0) or 0),
            near_miss_count=int(document.get("near_miss_count", 0) or 0),
            violation_count=int(document.get("violation_count", 0) or 0),
            top_risk_factors=list(document.get("top_risk_factors") or []),
            peak_hour=document.get("peak_hour"),
            last_event_at=document.get("last_event_at"),
            updated_at=document.get("updated_at"),
        )


class RiskZoneResponse(ResponseModel):
    """A scored area of road, derived from attributed events.

    Zones are computed, never hand-authored: a hand-placed "dangerous area"
    would be an opinion presented as a measurement.
    """

    id: str
    road_segment_id: str | None = None
    road_name: str | None = None
    centre: GeoPoint
    radius_m: float = Field(description="Influence radius used for driver alerts.")

    risk_score: float
    risk_level: RiskLevel
    confidence: float
    top_risk_factors: list[str] = Field(default_factory=list)

    event_count: int = 0
    near_miss_count: int = 0
    violation_count: int = 0
    dominant_event_type: EventType | None = None
    peak_hour: int | None = None

    #: Direction of travel this zone applies to. A hazard on the opposite
    #: carriageway is not a hazard for a driver going the other way.
    bearing_deg: float | None = None

    computed_at: datetime | None = None
    window_hours: int | None = None
    origin: str = "MEASURED"

    @classmethod
    def from_document(cls, document: dict) -> RiskZoneResponse:
        raw_centre = document.get("centre") or {}
        score = float(document.get("risk_score", 0.0) or 0.0)
        raw_dominant = document.get("dominant_event_type")

        return cls(
            id=str(document["id"]),
            road_segment_id=document.get("road_segment_id"),
            road_name=document.get("road_name"),
            centre=GeoPoint(
                latitude=float(raw_centre.get("latitude", 0.0)),
                longitude=float(raw_centre.get("longitude", 0.0)),
            ),
            radius_m=float(document.get("radius_m", 150.0) or 150.0),
            risk_score=score,
            risk_level=risk_level_from_score(score),
            confidence=float(document.get("confidence", 0.0) or 0.0),
            top_risk_factors=list(document.get("top_risk_factors") or []),
            event_count=int(document.get("event_count", 0) or 0),
            near_miss_count=int(document.get("near_miss_count", 0) or 0),
            violation_count=int(document.get("violation_count", 0) or 0),
            dominant_event_type=EventType(raw_dominant) if raw_dominant else None,
            peak_hour=document.get("peak_hour"),
            bearing_deg=document.get("bearing_deg"),
            computed_at=document.get("computed_at"),
            window_hours=document.get("window_hours"),
            origin=str(document.get("origin", "MEASURED")),
        )


class HourlyRiskPoint(ResponseModel):
    hour: int = Field(ge=0, le=23)
    risk_score: float
    risk_level: RiskLevel
    event_count: int


class SegmentDetailResponse(ResponseModel):
    """Everything the risk-map detail panel shows for one hotspot."""

    segment: RoadSegmentResponse
    risk_by_hour: list[HourlyRiskPoint] = Field(default_factory=list)
    event_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_events: list[dict] = Field(default_factory=list)
    cameras: list[dict] = Field(default_factory=list)


class NearbyRiskRequest(ApiModel):
    """A driver position, for the alert engine."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    heading_deg: float | None = Field(
        default=None,
        ge=0,
        lt=360,
        description=(
            "Direction of travel. Without it, direction relevance cannot be applied and "
            "every nearby zone is returned regardless of whether it is ahead."
        ),
    )
    speed_kmh: float | None = Field(default=None, ge=0, le=300)
    radius_m: float = Field(default=1000, gt=0, le=5000)


class NearbyZone(ResponseModel):
    """A risk zone near the driver, with the geometry the alert engine used."""

    zone: RiskZoneResponse
    distance_m: float
    bearing_deg: float = Field(description="Bearing from the driver to the zone.")
    is_ahead: bool = Field(
        description="False when the zone is behind the driver or off their heading."
    )
    eta_seconds: float | None = Field(
        default=None, description="Seconds until arrival at the current speed, when speed is known."
    )


class AlertResponse(ResponseModel):
    """A warning the driver app should raise."""

    zone_id: str
    level: AlertLevel
    risk_score: float
    risk_level: RiskLevel
    distance_m: float
    road_name: str | None = None
    headline: str = Field(description="Short spoken line, e.g. 'High collision risk ahead.'")
    detail: str | None = None
    factors: list[str] = Field(
        default_factory=list, description="Why, in plain words. Shown on the alert card."
    )
    recommendations: list[str] = Field(default_factory=list)
    cooldown_seconds: int
    origin: str = "MEASURED"


class AlertEvaluationResponse(ResponseModel):
    evaluated_at: datetime
    position: GeoPoint
    heading_deg: float | None = None
    current_segment_id: str | None = Field(
        default=None, description="Road segment the driver was matched to, if any."
    )
    current_segment_name: str | None = None
    nearby: list[NearbyZone] = Field(default_factory=list)
    alert: AlertResponse | None = Field(
        default=None, description="Null when nothing warrants a warning."
    )
    suppressed_reason: str | None = Field(
        default=None,
        description="Why no alert was raised when a zone was nearby: behind the driver, below threshold, or within cooldown.",
    )
