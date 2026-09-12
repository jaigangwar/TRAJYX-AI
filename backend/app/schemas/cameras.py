"""Camera registry schemas.

A camera is not just a video source: it carries the geometry that decides what
the analysis is even *allowed* to conclude. Without a stop line there is no
red-light violation; without lane direction there is no wrong-way detection;
without calibration there is no speed estimate. Those fields are optional here
and their absence is honoured downstream — a detector reports
`UNABLE_TO_DETERMINE` rather than guessing.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator
from trajyx_shared.domain import CameraStatus, RiskLevel, SignalState, risk_level_from_score

from app.schemas.common import ApiModel, GeoPoint, ResponseModel


class PixelPoint(ApiModel):
    """A point in the camera image, in pixels from the top-left."""

    x: float = Field(ge=0)
    y: float = Field(ge=0)


class StopLine(ApiModel):
    """The stop line, as two image-space endpoints.

    Configuring this is what enables stop-line and red-light violation
    detection for a camera. Absent, both are reported as unavailable.
    """

    start: PixelPoint
    end: PixelPoint


class LaneDirection(ApiModel):
    """Expected direction of travel for one lane, and where that lane is.

    `heading_deg` is degrees clockwise from image-up, the same convention the
    CV pipeline uses, so a tracked heading compares directly.

    The `region_y` band is what makes wrong-way detection usable. Comparing a
    heading against the closest configured heading is useless on a two-way
    road: a car driving east in the westbound lane matches the eastbound lane
    perfectly. The lane a vehicle occupies has to be decided by position
    first. Without a region, wrong-way detection reports itself unavailable
    rather than guessing.
    """

    lane_index: int = Field(ge=0)
    heading_deg: float = Field(ge=0, lt=360)
    label: str | None = Field(default=None, max_length=60)
    region_y_min: float | None = Field(
        default=None, ge=0, description="Top of the lane band, in image pixels."
    )
    region_y_max: float | None = Field(
        default=None, ge=0, description="Bottom of the lane band, in image pixels."
    )

    @field_validator("region_y_max")
    @classmethod
    def _band_is_ordered(cls, value: float | None, info) -> float | None:
        minimum = info.data.get("region_y_min")
        if value is not None and minimum is not None and value <= minimum:
            raise ValueError("region_y_max must be greater than region_y_min")
        return value


class Calibration(ApiModel):
    """Image-to-ground scale, which is what gates speed estimation.

    `metres_per_pixel_at_reference` applies at `reference_y` in the image; a
    road-facing camera compresses distance with depth, so one scalar is an
    approximation and any speed derived from it is reported as ESTIMATED,
    never as measured.
    """

    metres_per_pixel_at_reference: float = Field(
        gt=0, description="Ground metres per image pixel at reference_y."
    )
    reference_y: float = Field(ge=0, description="Image row the scale was measured at.")
    notes: str | None = Field(default=None, max_length=500)


class CameraBase(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    location: GeoPoint
    description: str | None = Field(default=None, max_length=500)
    road_segment_id: str | None = Field(
        default=None, description="Road segment this camera observes."
    )
    road_name: str | None = Field(default=None, max_length=160)

    stream_url: str | None = Field(
        default=None, description="RTSP or HTTP stream. Null for upload-only cameras."
    )
    frame_width: int | None = Field(default=None, gt=0)
    frame_height: int | None = Field(default=None, gt=0)
    frame_rate: float | None = Field(default=None, gt=0)

    stop_line: StopLine | None = None
    lane_directions: list[LaneDirection] = Field(default_factory=list)
    calibration: Calibration | None = None

    signal_state: SignalState = Field(
        default=SignalState.UNKNOWN,
        description=(
            "Current signal phase. UNKNOWN suppresses red-light detection "
            "entirely rather than assuming a phase."
        ),
    )

    @field_validator("lane_directions")
    @classmethod
    def _unique_lane_indexes(cls, lanes: list[LaneDirection]) -> list[LaneDirection]:
        indexes = [lane.lane_index for lane in lanes]
        if len(set(indexes)) != len(indexes):
            raise ValueError("lane_index values must be unique")
        return lanes


class CameraCreate(CameraBase):
    """A camera being registered."""


class CameraUpdate(ApiModel):
    """A partial camera edit. Every field optional; omitted fields are untouched."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    location: GeoPoint | None = None
    description: str | None = Field(default=None, max_length=500)
    road_segment_id: str | None = None
    road_name: str | None = Field(default=None, max_length=160)
    stream_url: str | None = None
    frame_width: int | None = Field(default=None, gt=0)
    frame_height: int | None = Field(default=None, gt=0)
    frame_rate: float | None = Field(default=None, gt=0)
    stop_line: StopLine | None = None
    lane_directions: list[LaneDirection] | None = None
    calibration: Calibration | None = None
    status: CameraStatus | None = None
    signal_state: SignalState | None = None


class CameraCapabilities(ResponseModel):
    """What this camera's configuration actually permits.

    Surfaced so an operator can see *why* a camera reports no wrong-way events:
    because no lane direction is configured, not because there were none.
    """

    speed_estimation: bool = Field(description="Requires calibration.")
    wrong_way_detection: bool = Field(
        description="Requires at least one lane with both a heading and an image y band."
    )
    stop_line_violation: bool = Field(description="Requires a stop line.")
    red_light_violation: bool = Field(description="Requires a stop line and a known signal phase.")

    @classmethod
    def derive(cls, document: dict[str, object]) -> CameraCapabilities:
        has_stop_line = isinstance(document.get("stop_line"), dict)
        lanes = document.get("lane_directions")
        # A heading alone is not enough: without a region the detector cannot
        # tell which lane a vehicle is in, so it reports unavailable.
        has_lanes = isinstance(lanes, list) and any(
            isinstance(lane, dict)
            and lane.get("region_y_min") is not None
            and lane.get("region_y_max") is not None
            for lane in lanes
        )
        signal_known = str(document.get("signal_state", SignalState.UNKNOWN.value)) != (
            SignalState.UNKNOWN.value
        )
        return cls(
            speed_estimation=isinstance(document.get("calibration"), dict),
            wrong_way_detection=has_lanes,
            stop_line_violation=has_stop_line,
            red_light_violation=has_stop_line and signal_known,
        )


class CameraResponse(ResponseModel):
    id: str
    name: str
    location: GeoPoint
    description: str | None = None
    road_segment_id: str | None = None
    road_name: str | None = None

    status: CameraStatus
    signal_state: SignalState

    stream_url: str | None = None
    frame_width: int | None = None
    frame_height: int | None = None
    frame_rate: float | None = None

    stop_line: StopLine | None = None
    lane_directions: list[LaneDirection] = Field(default_factory=list)
    calibration: Calibration | None = None
    capabilities: CameraCapabilities

    current_risk_score: float | None = Field(
        default=None,
        description="Most recent risk score for this camera. Null until analysis has run.",
    )
    current_risk_level: RiskLevel | None = None
    last_event_at: datetime | None = None
    last_seen_at: datetime | None = Field(
        default=None, description="Last time the camera was reachable or produced a frame."
    )

    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_document(cls, document: dict[str, object]) -> CameraResponse:
        raw_location = document.get("location") or {}
        raw_score = document.get("current_risk_score")
        score = float(raw_score) if isinstance(raw_score, int | float) else None

        raw_lanes = document.get("lane_directions")
        lanes = [LaneDirection(**lane) for lane in raw_lanes] if isinstance(raw_lanes, list) else []

        raw_stop_line = document.get("stop_line")
        raw_calibration = document.get("calibration")

        return cls(
            id=str(document["id"]),
            name=str(document.get("name", "")),
            location=GeoPoint(
                latitude=float(raw_location.get("latitude", 0.0)),  # type: ignore[union-attr]
                longitude=float(raw_location.get("longitude", 0.0)),  # type: ignore[union-attr]
            ),
            description=document.get("description"),  # type: ignore[arg-type]
            road_segment_id=document.get("road_segment_id"),  # type: ignore[arg-type]
            road_name=document.get("road_name"),  # type: ignore[arg-type]
            status=CameraStatus(str(document.get("status", CameraStatus.OFFLINE.value))),
            signal_state=SignalState(str(document.get("signal_state", SignalState.UNKNOWN.value))),
            stream_url=document.get("stream_url"),  # type: ignore[arg-type]
            frame_width=document.get("frame_width"),  # type: ignore[arg-type]
            frame_height=document.get("frame_height"),  # type: ignore[arg-type]
            frame_rate=document.get("frame_rate"),  # type: ignore[arg-type]
            stop_line=StopLine(**raw_stop_line) if isinstance(raw_stop_line, dict) else None,
            lane_directions=lanes,
            calibration=Calibration(**raw_calibration) if isinstance(raw_calibration, dict) else None,
            capabilities=CameraCapabilities.derive(document),
            current_risk_score=score,
            current_risk_level=risk_level_from_score(score) if score is not None else None,
            last_event_at=document.get("last_event_at"),  # type: ignore[arg-type]
            last_seen_at=document.get("last_seen_at"),  # type: ignore[arg-type]
            created_at=document.get("created_at"),  # type: ignore[arg-type]
            updated_at=document.get("updated_at"),  # type: ignore[arg-type]
        )
