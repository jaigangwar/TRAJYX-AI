"""Safety and violation detectors.

Each detector declares what configuration it needs and reports
``UNAVAILABLE`` when that configuration is absent. That is the whole design:
an unconfigured camera must produce "cannot determine", not "no violations",
because the two look identical on a dashboard and only one of them is true.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from trajyx_cv.trajectory.motion import (
    Calibration,
    MotionSample,
    dominant_heading,
    mean_position,
    representative_width,
)
from trajyx_cv.types import BoundingBox, Point, Track, angular_difference
from trajyx_shared.domain import Determination, EventType, Severity, SignalState, VehicleClass


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class Finding:
    """One detector output for one track."""

    event_type: EventType
    track_id: int
    frame_index: int
    timestamp_s: float
    confidence: float
    severity: Severity = Severity.MINOR
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DetectorResult:
    """What a detector concluded, including being unable to conclude."""

    name: str
    availability: Availability
    findings: tuple[Finding, ...] = ()
    #: Why the detector could not run. Surfaced to operators verbatim.
    unavailable_reason: str | None = None

    @staticmethod
    def unavailable(name: str, reason: str) -> DetectorResult:
        return DetectorResult(name=name, availability=Availability.UNAVAILABLE, unavailable_reason=reason)

    @staticmethod
    def available(name: str, findings: list[Finding]) -> DetectorResult:
        return DetectorResult(name=name, availability=Availability.AVAILABLE, findings=tuple(findings))


@dataclass(frozen=True, slots=True)
class StopLineGeometry:
    start: Point
    end: Point

    def side_of(self, point: Point) -> float:
        """Signed cross product: which side of the line the point lies on."""
        return (self.end.x - self.start.x) * (point.y - self.start.y) - (
            self.end.y - self.start.y
        ) * (point.x - self.start.x)


@dataclass(frozen=True, slots=True)
class LaneDirection:
    """Expected direction of travel for one lane, and where that lane is.

    ``region`` is what makes wrong-way detection actually work. Comparing a
    heading against the *closest* configured heading is useless on a two-way
    road: a car driving east in the westbound lane matches the eastbound lane
    perfectly and is declared fine. The lane a vehicle is *in* must be decided
    by position first, and only then is its heading judged.

    The region is an image-space band, the y range the lane occupies. That
    suits a road-facing camera, where lanes stack vertically in frame. Without
    a region, wrong-way detection reports itself unavailable rather than
    guessing.
    """

    lane_index: int
    heading_deg: float
    region_y_min: float | None = None
    region_y_max: float | None = None

    @property
    def has_region(self) -> bool:
        return self.region_y_min is not None and self.region_y_max is not None

    def distance_to(self, point: Point) -> float:
        """Vertical distance from the lane band, 0 when inside it."""
        if self.region_y_min is None or self.region_y_max is None:
            return float("inf")
        if point.y < self.region_y_min:
            return self.region_y_min - point.y
        if point.y > self.region_y_max:
            return point.y - self.region_y_max
        return 0.0


@dataclass(frozen=True, slots=True)
class CameraContext:
    """Everything a detector may need to know about the source camera."""

    calibration: Calibration | None = None
    stop_line: StopLineGeometry | None = None
    lane_directions: tuple[LaneDirection, ...] = ()
    signal_state: SignalState = SignalState.UNKNOWN
    speed_limit_kmh: float | None = None
    frame_width: int = 1920
    frame_height: int = 1080


# ---------------------------------------------------------------- thresholds
# Chosen from road-safety literature rather than tuned to look impressive.

#: Deceleration beyond this is a hard brake. ~0.4 g; normal comfortable braking
#: is under 2 m/s^2, emergency braking reaches 6-8 m/s^2.
HARD_BRAKING_MS2 = 4.0

#: Acceleration beyond this is abrupt. Sustained acceleration above ~3 m/s^2 is
#: aggressive for a passenger car.
SUDDEN_ACCELERATION_MS2 = 3.5

#: Heading must oppose the lane by more than this to count as wrong-way.
#: 120 degrees rather than 180 so a vehicle cutting across at an angle still
#: registers, while a lane change (typically under 45) does not.
WRONG_WAY_MIN_ANGLE_DEG = 120.0

#: A wrong-way track must persist this long. A single frame of bad heading is
#: noise; three seconds of opposing travel is a vehicle going the wrong way.
WRONG_WAY_MIN_DURATION_S = 1.5

#: Lateral movement, as a fraction of the vehicle's own width, that counts as a
#: lane change within the window below.
LANE_CHANGE_WIDTH_FRACTION = 1.2
LANE_CHANGE_WINDOW_S = 2.0

#: Overspeed tolerance over the posted limit, absorbing estimation error.
OVERSPEED_TOLERANCE_KMH = 10.0

#: A pedestrian this close to a moving vehicle is a conflict, in metres.
PEDESTRIAN_CONFLICT_DISTANCE_M = 2.5


def _ms2_from_kmh_s(value: float) -> float:
    return value / 3.6


# ------------------------------------------------------------------ detectors


def detect_hard_braking(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    name = "hard_braking"
    if context.calibration is None:
        return DetectorResult.unavailable(
            name, "Camera is not calibrated, so deceleration cannot be expressed in m/s^2."
        )

    findings: list[Finding] = []
    for sample in samples:
        if sample.acceleration_kmh_s is None:
            continue
        deceleration = -_ms2_from_kmh_s(sample.acceleration_kmh_s)
        if deceleration >= HARD_BRAKING_MS2:
            findings.append(
                Finding(
                    event_type=EventType.HARD_BRAKING,
                    track_id=track.track_id,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    # Confidence rises with how far past the threshold it is,
                    # capped: this is a geometric estimate, not a measurement.
                    confidence=min(0.9, 0.5 + (deceleration - HARD_BRAKING_MS2) / 20.0),
                    severity=Severity.MAJOR if deceleration >= 6.0 else Severity.MINOR,
                    details={
                        "deceleration_ms2": round(deceleration, 2),
                        "speed_kmh": round(sample.speed_kmh, 1) if sample.speed_kmh else None,
                        "threshold_ms2": HARD_BRAKING_MS2,
                    },
                )
            )
    return DetectorResult.available(name, _dedupe(findings))


def detect_sudden_acceleration(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    name = "sudden_acceleration"
    if context.calibration is None:
        return DetectorResult.unavailable(
            name, "Camera is not calibrated, so acceleration cannot be expressed in m/s^2."
        )

    findings: list[Finding] = []
    for sample in samples:
        if sample.acceleration_kmh_s is None:
            continue
        acceleration = _ms2_from_kmh_s(sample.acceleration_kmh_s)
        if acceleration >= SUDDEN_ACCELERATION_MS2:
            findings.append(
                Finding(
                    event_type=EventType.SUDDEN_ACCELERATION,
                    track_id=track.track_id,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    confidence=min(0.85, 0.5 + (acceleration - SUDDEN_ACCELERATION_MS2) / 20.0),
                    details={
                        "acceleration_ms2": round(acceleration, 2),
                        "threshold_ms2": SUDDEN_ACCELERATION_MS2,
                    },
                )
            )
    return DetectorResult.available(name, _dedupe(findings))


def detect_wrong_way(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    """Travel opposing the direction of the lane the vehicle is occupying.

    The lane is chosen by *position*, then the heading is compared only against
    that lane. Comparing against the nearest matching heading instead declares
    a wrong-way car correct whenever any lane happens to run the way it is
    going, which is every two-way road.
    """
    name = "wrong_way"
    if not context.lane_directions:
        return DetectorResult.unavailable(
            name, "No lane direction configured for this camera, so wrong-way travel is undefined."
        )

    with_regions = [lane for lane in context.lane_directions if lane.has_region]
    if not with_regions:
        return DetectorResult.unavailable(
            name,
            "Lane headings are configured but lane regions are not, so the lane a vehicle "
            "occupies cannot be determined. Set each lane's image y range to enable this check.",
        )

    heading = dominant_heading(samples)
    position = mean_position(samples)
    if heading is None or position is None:
        return DetectorResult.available(name, [])

    lane = min(with_regions, key=lambda item: item.distance_to(position))
    difference = angular_difference(heading, lane.heading_deg)

    if difference < WRONG_WAY_MIN_ANGLE_DEG or track.duration_s < WRONG_WAY_MIN_DURATION_S:
        return DetectorResult.available(name, [])

    last = track.points[-1]
    return DetectorResult.available(
        name,
        [
            Finding(
                event_type=EventType.WRONG_WAY,
                track_id=track.track_id,
                frame_index=last.frame_index,
                timestamp_s=last.timestamp_s,
                confidence=min(0.95, 0.6 + (difference - WRONG_WAY_MIN_ANGLE_DEG) / 120.0),
                severity=Severity.CRITICAL,
                details={
                    "track_heading_deg": round(heading, 1),
                    "lane_index": lane.lane_index,
                    "lane_heading_deg": lane.heading_deg,
                    "angular_difference_deg": round(difference, 1),
                    "duration_s": round(track.duration_s, 2),
                },
            )
        ],
    )


def detect_stop_line_violation(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    name = "stop_line_violation"
    if context.stop_line is None:
        return DetectorResult.unavailable(name, "No stop line configured for this camera.")

    findings: list[Finding] = []
    previous_side: float | None = None

    for sample in samples:
        side = context.stop_line.side_of(sample.position)
        if previous_side is not None and previous_side * side < 0:
            findings.append(
                Finding(
                    event_type=EventType.STOP_LINE_VIOLATION,
                    track_id=track.track_id,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    confidence=0.75,
                    details={"crossed_at_s": round(sample.timestamp_s, 2)},
                )
            )
            break
        previous_side = side

    return DetectorResult.available(name, findings)


def detect_red_light_violation(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    """Stop-line crossing while the signal is red.

    Refuses to run when the phase is UNKNOWN. Assuming a phase would let the
    system issue a red-light violation it has no evidence for, which is the
    single most consequential thing it could get wrong.
    """
    name = "red_light_violation"
    if context.stop_line is None:
        return DetectorResult.unavailable(name, "No stop line configured for this camera.")
    if context.signal_state is SignalState.UNKNOWN:
        return DetectorResult.unavailable(
            name,
            "Signal phase is unknown for this camera. Red-light violations are not inferred "
            "without a known phase.",
        )
    if context.signal_state is not SignalState.RED:
        return DetectorResult.available(name, [])

    crossing = detect_stop_line_violation(track, samples, context)
    findings = [
        Finding(
            event_type=EventType.RED_LIGHT_VIOLATION,
            track_id=finding.track_id,
            frame_index=finding.frame_index,
            timestamp_s=finding.timestamp_s,
            confidence=finding.confidence * 0.95,
            severity=Severity.CRITICAL,
            details={**finding.details, "signal_state": context.signal_state.value},
        )
        for finding in crossing.findings
    ]
    return DetectorResult.available(name, findings)


def detect_overspeed(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    name = "overspeed"
    if context.calibration is None:
        return DetectorResult.unavailable(
            name, "Camera is not calibrated, so speed cannot be estimated."
        )
    if context.speed_limit_kmh is None:
        return DetectorResult.unavailable(name, "No speed limit configured for this camera.")

    limit = context.speed_limit_kmh + OVERSPEED_TOLERANCE_KMH
    findings: list[Finding] = []
    for sample in samples:
        if sample.speed_kmh is not None and sample.speed_kmh > limit:
            findings.append(
                Finding(
                    event_type=EventType.OVERSPEED,
                    track_id=track.track_id,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    confidence=0.6,  # bounded: an estimate from one scalar scale
                    severity=Severity.MAJOR,
                    details={
                        "estimated_speed_kmh": round(sample.speed_kmh, 1),
                        "speed_limit_kmh": context.speed_limit_kmh,
                        "tolerance_kmh": OVERSPEED_TOLERANCE_KMH,
                        "measurement": "ESTIMATED",
                    },
                )
            )
    return DetectorResult.available(name, _dedupe(findings))


def detect_dangerous_lane_change(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> DetectorResult:
    """Abrupt lateral displacement relative to the vehicle's own width."""
    name = "dangerous_lane_change"
    del context

    if len(samples) < 4:
        return DetectorResult.available(name, [])

    findings: list[Finding] = []
    for index, sample in enumerate(samples):
        window = [
            other
            for other in samples[index:]
            if other.timestamp_s - sample.timestamp_s <= LANE_CHANGE_WINDOW_S
        ]
        if len(window) < 3:
            continue

        heading = sample.heading_deg
        if heading is None:
            continue

        # Median width, not the per-frame box: a vehicle entering or leaving
        # the frame has a clipped box, which made a 78px car measure 11px and
        # turned ordinary travel into a "dangerous lane change".
        width = representative_width(track)
        if width <= 1:
            continue

        lateral = _lateral_displacement(sample.position, window[-1].position, heading)
        if abs(lateral) >= width * LANE_CHANGE_WIDTH_FRACTION:
            findings.append(
                Finding(
                    event_type=EventType.DANGEROUS_LANE_CHANGE,
                    track_id=track.track_id,
                    frame_index=sample.frame_index,
                    timestamp_s=sample.timestamp_s,
                    confidence=0.55,
                    details={
                        "lateral_displacement_px": round(abs(lateral), 1),
                        "vehicle_width_px": round(width, 1),
                        "window_s": LANE_CHANGE_WINDOW_S,
                    },
                )
            )
    return DetectorResult.available(name, _dedupe(findings, min_gap_s=LANE_CHANGE_WINDOW_S))


def detect_helmet(track: Track, _samples: list[MotionSample], _context: CameraContext) -> DetectorResult:
    """Helmet compliance for a motorcycle or scooter rider.

    Deliberately unavailable. Helmet detection needs a model trained on
    rider-head crops, and the stock COCO weights have no such class. Inferring
    it from the vehicle box would be a fabricated determination about a real
    person's compliance, so the detector reports that it cannot run.
    """
    name = "helmet"
    if track.vehicle_class not in {VehicleClass.MOTORCYCLE, VehicleClass.SCOOTER}:
        return DetectorResult.available(name, [])

    return DetectorResult.unavailable(
        name,
        "No helmet-detection model is registered. The stock detector has no helmet class, and "
        "helmet compliance is not inferred from the vehicle box. Register a trained model to "
        "enable this check.",
    )


def detect_seatbelt(
    track: Track, _samples: list[MotionSample], _context: CameraContext
) -> DetectorResult:
    """Seatbelt compliance. Unavailable for the same reason as helmets, plus
    seatbelts are usually not visible at all from a road-facing camera."""
    name = "seatbelt"
    if track.vehicle_class not in {VehicleClass.CAR, VehicleClass.VAN, VehicleClass.TRUCK}:
        return DetectorResult.available(name, [])

    return DetectorResult.unavailable(
        name,
        "No seatbelt-detection model is registered, and a road-facing camera rarely has the "
        "cabin visibility required. Result is UNABLE_TO_DETERMINE.",
    )


def detect_triple_riding(
    track: Track, _samples: list[MotionSample], _context: CameraContext
) -> DetectorResult:
    """Occupant count on a two-wheeler. Needs a rider-counting model."""
    name = "triple_riding"
    if track.vehicle_class not in {VehicleClass.MOTORCYCLE, VehicleClass.SCOOTER}:
        return DetectorResult.available(name, [])

    return DetectorResult.unavailable(
        name,
        "No occupant-counting model is registered. Rider count is not inferred from box size.",
    )


def determination_for(result: DetectorResult) -> Determination:
    """Map a detector result to the tri-state determination.

    An unavailable detector yields UNABLE_TO_DETERMINE, never NOT_DETECTED.
    """
    if result.availability is Availability.UNAVAILABLE:
        return Determination.UNABLE_TO_DETERMINE
    return Determination.DETECTED if result.findings else Determination.NOT_DETECTED


# ------------------------------------------------------------------- registry

BEHAVIOUR_DETECTORS = (
    detect_hard_braking,
    detect_sudden_acceleration,
    detect_dangerous_lane_change,
)

VIOLATION_DETECTORS = (
    detect_wrong_way,
    detect_stop_line_violation,
    detect_red_light_violation,
    detect_overspeed,
)

VISUAL_DETECTORS = (
    detect_helmet,
    detect_seatbelt,
    detect_triple_riding,
)

ALL_DETECTORS = BEHAVIOUR_DETECTORS + VIOLATION_DETECTORS + VISUAL_DETECTORS


def run_all(
    track: Track, samples: list[MotionSample], context: CameraContext
) -> list[DetectorResult]:
    return [detector(track, samples, context) for detector in ALL_DETECTORS]


# -------------------------------------------------------------------- helpers


def _dedupe(findings: list[Finding], min_gap_s: float = 1.0) -> list[Finding]:
    """Collapse repeats of the same event within `min_gap_s`.

    One hard brake spans several frames; reporting each frame would inflate the
    counts by an order of magnitude.
    """
    if not findings:
        return []
    kept = [findings[0]]
    for finding in findings[1:]:
        if finding.timestamp_s - kept[-1].timestamp_s >= min_gap_s:
            kept.append(finding)
        elif finding.confidence > kept[-1].confidence:
            kept[-1] = finding  # keep the strongest instance of the burst
    return kept


def _lateral_displacement(start: Point, end: Point, heading_deg: float) -> float:
    """Component of movement perpendicular to `heading_deg`."""
    import math

    radians = math.radians(heading_deg)
    # Heading is clockwise from image-up, so the forward unit vector in image
    # space is (sin, -cos) and the perpendicular is (cos, sin).
    perpendicular_x = math.cos(radians)
    perpendicular_y = math.sin(radians)
    return (end.x - start.x) * perpendicular_x + (end.y - start.y) * perpendicular_y


def pedestrian_conflict_distance_px(calibration: Calibration | None, y: float) -> float | None:
    """The conflict threshold in pixels, or None when uncalibrated."""
    if calibration is None:
        return None
    scale = calibration.metres_per_pixel_at(y)
    return PEDESTRIAN_CONFLICT_DISTANCE_M / scale if scale > 0 else None


def box_gap_px(first: BoundingBox, second: BoundingBox) -> float:
    """Shortest gap between two boxes, 0 when they overlap."""
    dx = max(0.0, max(first.x1 - second.x2, second.x1 - first.x2))
    dy = max(0.0, max(first.y1 - second.y2, second.y1 - first.y2))
    return (dx**2 + dy**2) ** 0.5
