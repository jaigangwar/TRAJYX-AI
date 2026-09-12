"""
TRAJYX generated file - DO NOT EDIT BY HAND.
Source: shared/contracts/domain.json
Regenerate: python scripts/gen_contracts.py
"""

from __future__ import annotations

from enum import Enum
from typing import Final

CONTRACT_VERSION: Final[str] = "1.0.0"


class Role(str, Enum):
    """Authorization roles. Ordered from most to least privileged."""

    ADMIN = "ADMIN"
    TRAFFIC_OPERATOR = "TRAFFIC_OPERATOR"
    ANALYST = "ANALYST"
    DRIVER = "DRIVER"


class RiskLevel(str, Enum):
    """Coarse risk band derived from a 0-100 risk score."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Severity(str, Enum):
    """Event severity, independent of the numeric risk score."""

    INFO = "INFO"
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """Canonical event taxonomy emitted by the safety, interaction and risk engines."""

    HELMET_VIOLATION = "HELMET_VIOLATION"
    SEATBELT_VIOLATION = "SEATBELT_VIOLATION"
    TRIPLE_RIDING = "TRIPLE_RIDING"
    WRONG_WAY = "WRONG_WAY"
    RED_LIGHT_VIOLATION = "RED_LIGHT_VIOLATION"
    STOP_LINE_VIOLATION = "STOP_LINE_VIOLATION"
    DANGEROUS_LANE_CHANGE = "DANGEROUS_LANE_CHANGE"
    OVERSPEED = "OVERSPEED"
    HARD_BRAKING = "HARD_BRAKING"
    SUDDEN_ACCELERATION = "SUDDEN_ACCELERATION"
    DISTRACTED_RIDING = "DISTRACTED_RIDING"
    PEDESTRIAN_CONFLICT = "PEDESTRIAN_CONFLICT"
    NEAR_MISS = "NEAR_MISS"
    COLLISION_RISK = "COLLISION_RISK"
    HAZARD_REPORT = "HAZARD_REPORT"


class EventCategory(str, Enum):
    """Grouping used by dashboard navigation and reporting."""

    VIOLATION = "VIOLATION"
    BEHAVIOR = "BEHAVIOR"
    INTERACTION = "INTERACTION"
    REPORT = "REPORT"


class VehicleClass(str, Enum):
    """Detector output classes. Extend by adding here and retraining/remapping the detector."""

    CAR = "CAR"
    MOTORCYCLE = "MOTORCYCLE"
    SCOOTER = "SCOOTER"
    BUS = "BUS"
    TRUCK = "TRUCK"
    AUTO_RICKSHAW = "AUTO_RICKSHAW"
    VAN = "VAN"
    BICYCLE = "BICYCLE"
    PEDESTRIAN = "PEDESTRIAN"


class CameraStatus(str, Enum):
    """Operational state of a camera as shown in Live Monitoring."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    PROCESSING = "PROCESSING"
    ALERT = "ALERT"


class JobStatus(str, Enum):
    """Lifecycle of an asynchronous video analysis job."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TtcBand(str, Enum):
    """Band for an ESTIMATED time-to-collision value. Always presented as an estimate."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Determination(str, Enum):
    """Tri-state result for any visual check. UNABLE_TO_DETERMINE is a first-class outcome and must never be collapsed into a negative."""

    DETECTED = "DETECTED"
    NOT_DETECTED = "NOT_DETECTED"
    UNABLE_TO_DETERMINE = "UNABLE_TO_DETERMINE"


class AlertLevel(str, Enum):
    """Driver alert escalation tiers."""

    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"


class DataOrigin(str, Enum):
    """Provenance label. Every record carries one so simulated and estimated values are never displayed as measured ground truth."""

    MEASURED = "MEASURED"
    ESTIMATED = "ESTIMATED"
    DEMO = "DEMO"


class HazardType(str, Enum):
    """Hazard categories a driver can report from the mobile app."""

    ACCIDENT = "ACCIDENT"
    POTHOLE = "POTHOLE"
    BROKEN_SIGNAL = "BROKEN_SIGNAL"
    ROAD_BLOCKAGE = "ROAD_BLOCKAGE"
    WRONG_WAY_VEHICLE = "WRONG_WAY_VEHICLE"
    DANGEROUS_CROSSING = "DANGEROUS_CROSSING"
    POOR_VISIBILITY = "POOR_VISIBILITY"
    ROAD_DAMAGE = "ROAD_DAMAGE"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    """Review workflow state for driver hazard reports and flagged violations."""

    PENDING = "PENDING"
    REVIEWING = "REVIEWING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ModelHealth(str, Enum):
    """Operational health of a registered model version."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    UNKNOWN = "UNKNOWN"


class SignalState(str, Enum):
    """Traffic signal phase used by the red-light violation detector. UNKNOWN suppresses red-light detection entirely."""

    RED = "RED"
    AMBER = "AMBER"
    GREEN = "GREEN"
    UNKNOWN = "UNKNOWN"


RISK_BANDS: Final[tuple[tuple[RiskLevel, int, int], ...]] = (
    (RiskLevel.LOW, 0, 25),
    (RiskLevel.MODERATE, 26, 50),
    (RiskLevel.HIGH, 51, 75),
    (RiskLevel.CRITICAL, 76, 100),
)

TTC_BANDS: Final[tuple[tuple[TtcBand, float, float | None], ...]] = (
    (TtcBand.LOW, 5.0, None),
    (TtcBand.MEDIUM, 2.0, 5.0),
    (TtcBand.HIGH, 1.0, 2.0),
    (TtcBand.CRITICAL, 0.0, 1.0),
)

EVENT_CATEGORY: Final[dict[EventType, EventCategory]] = {
    EventType.HELMET_VIOLATION: EventCategory.VIOLATION,
    EventType.SEATBELT_VIOLATION: EventCategory.VIOLATION,
    EventType.TRIPLE_RIDING: EventCategory.VIOLATION,
    EventType.WRONG_WAY: EventCategory.VIOLATION,
    EventType.RED_LIGHT_VIOLATION: EventCategory.VIOLATION,
    EventType.STOP_LINE_VIOLATION: EventCategory.VIOLATION,
    EventType.DANGEROUS_LANE_CHANGE: EventCategory.VIOLATION,
    EventType.OVERSPEED: EventCategory.VIOLATION,
    EventType.HARD_BRAKING: EventCategory.BEHAVIOR,
    EventType.SUDDEN_ACCELERATION: EventCategory.BEHAVIOR,
    EventType.DISTRACTED_RIDING: EventCategory.BEHAVIOR,
    EventType.PEDESTRIAN_CONFLICT: EventCategory.INTERACTION,
    EventType.NEAR_MISS: EventCategory.INTERACTION,
    EventType.COLLISION_RISK: EventCategory.INTERACTION,
    EventType.HAZARD_REPORT: EventCategory.REPORT,
}

COLLECTIONS: Final[dict[str, str]] = {
    "users": "users",
    "cameras": "cameras",
    "video_jobs": "video_jobs",
    "video_analysis": "video_analysis",
    "detections": "detections",
    "tracking_events": "tracking_events",
    "violations": "violations",
    "near_misses": "near_misses",
    "risk_events": "risk_events",
    "road_segments": "road_segments",
    "risk_zones": "risk_zones",
    "alerts": "alerts",
    "driver_reports": "driver_reports",
    "notifications": "notifications",
    "model_versions": "model_versions",
    "analytics": "analytics",
    "settings": "settings",
    "trips": "trips",
}

ALERT_DEFAULTS: Final[dict] = {
    "level_1_min_risk": 50,
    "level_2_min_risk": 75,
    "level_3_min_risk": 90,
    "max_lateral_distance_m": 120,
    "approach_distance_m": {
        "LEVEL_1": 400,
        "LEVEL_2": 600,
        "LEVEL_3": 900
    },
    "bearing_tolerance_deg": 60,
    "cooldown_seconds": {
        "LEVEL_1": 300,
        "LEVEL_2": 180,
        "LEVEL_3": 120
    },
    "min_speed_kmh": 5
}


def risk_level_from_score(score: float) -> RiskLevel:
    """Map a 0-100 risk score onto its band. Scores are clamped into range."""
    s = max(0.0, min(100.0, float(score)))
    for level, _low, high in RISK_BANDS:
        if s <= high:
            return level
    return RiskLevel.CRITICAL


def ttc_band_from_seconds(seconds: float | None) -> TtcBand | None:
    """Band an ESTIMATED time-to-collision. None when TTC is undefined or negative."""
    if seconds is None or seconds < 0:
        return None
    for band, low, high in TTC_BANDS:
        if seconds >= low and (high is None or seconds < high):
            return band
    return TtcBand.LOW
