"""Video job and analysis schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field
from trajyx_shared.domain import DataOrigin, JobStatus, RiskLevel

from app.schemas.common import ApiModel, ResponseModel


class JobProgress(ResponseModel):
    stage: str = Field(description="queued | detecting | analysing | storing | complete | failed")
    percent: float = Field(ge=0, le=100)
    frames_processed: int = 0
    frames_total: int = 0
    detections: int = 0
    active_tracks: int = 0


class AnalyseRequest(ApiModel):
    """Options for an analysis run."""

    frame_stride: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="Process every Nth frame. Defaults to the deployment setting.",
    )
    max_frames: int | None = Field(
        default=None, ge=1, description="Cap the frames analysed. Useful for a quick preview."
    )
    speed_limit_kmh: float | None = Field(
        default=None, gt=0, le=200, description="Enables overspeed detection when set."
    )
    simulate: bool = Field(
        default=False,
        description=(
            "Run the scripted scenario instead of real detection. Everything produced is "
            "labelled DEMO and is never presented as measured."
        ),
    )


class VideoJobResponse(ResponseModel):
    id: str
    status: JobStatus
    filename: str
    size_bytes: int
    content_type: str
    camera_id: str | None = None
    camera_name: str | None = None

    storage_key: str
    annotated_key: str | None = None

    progress: JobProgress | None = None
    error: str | None = None

    frame_stride: int | None = None
    origin: DataOrigin = DataOrigin.MEASURED

    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: str | None = None

    analysis_id: str | None = None

    @classmethod
    def from_document(cls, document: dict, camera_name: str | None = None) -> VideoJobResponse:
        raw_progress = document.get("progress")
        return cls(
            id=str(document["id"]),
            status=JobStatus(str(document.get("status", JobStatus.QUEUED.value))),
            filename=str(document.get("filename", "")),
            size_bytes=int(document.get("size_bytes", 0) or 0),
            content_type=str(document.get("content_type", "")),
            camera_id=document.get("camera_id"),
            camera_name=camera_name,
            storage_key=str(document.get("storage_key", "")),
            annotated_key=document.get("annotated_key"),
            progress=JobProgress(**raw_progress) if isinstance(raw_progress, dict) else None,
            error=document.get("error"),
            frame_stride=document.get("frame_stride"),
            origin=DataOrigin(str(document.get("origin", DataOrigin.MEASURED.value))),
            created_at=document.get("created_at"),
            started_at=document.get("started_at"),
            completed_at=document.get("completed_at"),
            created_by=document.get("created_by"),
            analysis_id=document.get("analysis_id"),
        )


class TrackSummary(ResponseModel):
    """One tracked object, for the analysis panel and trajectory overlay."""

    track_id: int
    vehicle_class: str
    first_frame: int
    last_frame: int
    duration_s: float
    point_count: int
    mean_speed_kmh: float | None = Field(
        default=None, description="Null when the camera is uncalibrated. Always an estimate."
    )
    heading_deg: float | None = None
    #: Downsampled ground-contact path, for drawing the trajectory.
    path: list[list[float]] = Field(default_factory=list)


class TimelineEntry(ResponseModel):
    """An event on the video timeline, for click-to-seek."""

    timestamp_s: float
    frame_index: int
    event_type: str
    severity: str
    track_ids: list[int]
    confidence: float | None = None
    risk_score: float | None = None
    label: str


class UnavailableCheck(ResponseModel):
    name: str
    reason: str


class VideoAnalysisResponse(ResponseModel):
    id: str
    job_id: str
    camera_id: str | None = None

    frame_width: int
    frame_height: int
    camera_calibration: dict[str, float] | None = Field(
        default=None,
        description="Camera ground-plane calibration snapshot. Null when unavailable or frame dimensions differ.",
    )
    calibration_note: str | None = None
    frame_rate: float
    frame_count: int
    duration_s: float
    frames_analysed: int
    frame_stride: int

    detector_name: str
    detector_version: str
    tracker_name: str
    inference_ms_per_frame: float | None = None
    wall_seconds: float = 0.0

    detection_count: int
    vehicle_count: int
    pedestrian_count: int
    class_counts: dict[str, int] = Field(default_factory=dict)
    unmapped_labels: dict[str, int] = Field(
        default_factory=dict,
        description="Detector labels with no mapping. A rise means model drift.",
    )

    track_count: int
    tracks: list[TrackSummary] = Field(default_factory=list)

    violation_count: int = 0
    behaviour_count: int = 0
    near_miss_count: int = 0
    minimum_ttc_s: float | None = Field(
        default=None, description="Lowest estimated time to collision. Always an estimate."
    )
    mean_interaction_score: float | None = None

    risk_score: float | None = None
    risk_level: RiskLevel | None = None
    risk_confidence: float | None = None
    risk_factors: list[dict] = Field(default_factory=list)
    top_risk_factors: list[str] = Field(default_factory=list)

    timeline: list[TimelineEntry] = Field(default_factory=list)
    unavailable_checks: list[UnavailableCheck] = Field(
        default_factory=list,
        description="Checks that could not run, and why. An absent result is not a negative one.",
    )

    origin: DataOrigin = DataOrigin.MEASURED
    annotated_key: str | None = None
    created_at: datetime | None = None

    @classmethod
    def from_document(cls, document: dict) -> VideoAnalysisResponse:
        return cls(**{key: value for key, value in document.items() if key in cls.model_fields})
