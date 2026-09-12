"""Core geometry and observation types for the TRAJYX vision pipeline.

These are plain dataclasses with ``slots=True`` rather than Pydantic models:
they are allocated per detection per frame, so a 10-minute clip at 25 fps
creates hundreds of thousands of them. Validation happens once at the API
boundary (``backend/app/schemas``), not in the inner loop.

Coordinate conventions, fixed once here so no downstream module has to guess:

* Pixel space is ``(x, y)`` with the origin at the **top-left** of the frame,
  x increasing right and y increasing down — OpenCV's convention.
* Boxes are ``xyxy``: ``(x1, y1)`` top-left, ``(x2, y2)`` bottom-right,
  in absolute pixels, inclusive of x1/y1 and exclusive of x2/y2.
* Angles are degrees in ``[0, 360)``, measured clockwise from image-up
  (negative y), matching compass bearing so image-space and geographic
  headings can be compared without a second convention.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from trajyx_shared.domain import Determination, VehicleClass

__all__ = [
    "BoundingBox",
    "Point",
    "Detection",
    "FrameMeta",
    "TrackPoint",
    "Track",
    "bearing_degrees",
    "angular_difference",
    "average_bearing",
    "normalize_bearing",
]


def normalize_bearing(degrees: float) -> float:
    """Wrap an angle into ``[0, 360)``.

    A plain ``% 360`` is not enough: for a tiny negative input such as the
    ``-1e-15`` that trigonometry routinely produces, it returns ``360.0``,
    which is outside the documented range and compares as far from ``0``. The
    epsilon check collapses that case back to zero.
    """
    wrapped = degrees % 360.0
    return 0.0 if wrapped >= 360.0 - 1e-9 else wrapped


@dataclass(frozen=True, slots=True)
class Point:
    """A point in pixel space."""

    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned box in absolute pixels, ``xyxy``."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError(f"Degenerate bounding box: {self!r} (x2/y2 must not precede x1/y1)")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Point:
        return Point((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)

    @property
    def bottom_center(self) -> Point:
        """Ground-contact reference point.

        For a road-facing camera the bottom edge of a vehicle box approximates
        where it meets the road surface, which projects to the ground plane far
        more accurately than the box centre. Speed and distance estimation use
        this point.
        """
        return Point((self.x1 + self.x2) / 2.0, self.y2)

    def iou(self, other: BoundingBox) -> float:
        """Intersection over union, the standard box-overlap measure."""
        inter_x1 = max(self.x1, other.x1)
        inter_y1 = max(self.y1, other.y1)
        inter_x2 = min(self.x2, other.x2)
        inter_y2 = min(self.y2, other.y2)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        intersection = inter_w * inter_h
        if intersection <= 0.0:
            return 0.0

        union = self.area + other.area - intersection
        return intersection / union if union > 0 else 0.0

    def contains(self, point: Point) -> bool:
        return self.x1 <= point.x < self.x2 and self.y1 <= point.y < self.y2

    def clip_to(self, width: int, height: int) -> BoundingBox:
        """Clamp to frame bounds. Detectors can return slightly out-of-frame boxes."""
        return BoundingBox(
            x1=max(0.0, min(self.x1, width)),
            y1=max(0.0, min(self.y1, height)),
            x2=max(0.0, min(self.x2, width)),
            y2=max(0.0, min(self.y2, height)),
        )

    def as_xyxy(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def as_xywh(self) -> tuple[float, float, float, float]:
        """Top-left plus size, the form most trackers expect."""
        return (self.x1, self.y1, self.width, self.height)


@dataclass(frozen=True, slots=True)
class FrameMeta:
    """Identity and timing of a single decoded frame."""

    index: int
    """Zero-based index in the source video, before any frame-stride sampling."""

    timestamp_s: float
    """Presentation time in seconds from the start of the video."""

    width: int
    height: int


@dataclass(slots=True)
class Detection:
    """One object observed in one frame, before any tracking is applied."""

    vehicle_class: VehicleClass
    confidence: float
    box: BoundingBox
    frame_index: int
    timestamp_s: float

    raw_class_name: str | None = None
    """Detector's own label, kept so class remapping stays auditable."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Detection confidence must be in [0, 1], got {self.confidence}")


@dataclass(slots=True)
class TrackPoint:
    """A tracked object's state at one point in time."""

    frame_index: int
    timestamp_s: float
    box: BoundingBox
    confidence: float

    speed_kmh: float | None = None
    """Estimated ground speed. ``None`` when the camera lacks the calibration
    needed to convert pixel motion into metres — never a guess."""

    heading_deg: float | None = None
    """Direction of travel in image space, degrees clockwise from image-up.
    ``None`` until the track has moved far enough for a stable estimate."""

    @property
    def position(self) -> Point:
        return self.box.bottom_center


@dataclass(slots=True)
class Track:
    """An object followed across frames under one stable identity.

    The id is an anonymous per-video counter. TRAJYX does not identify vehicles
    or people: no plate reading, no face recognition, and ids are not reused
    across videos or correlated between cameras.
    """

    track_id: int
    vehicle_class: VehicleClass
    points: list[TrackPoint] = field(default_factory=list)

    class_votes: dict[VehicleClass, int] = field(default_factory=dict)
    """Per-frame class predictions. A motorcycle briefly misread as a bicycle
    should not change the track's class, so the majority vote wins."""

    helmet: Determination = Determination.UNABLE_TO_DETERMINE
    seatbelt: Determination = Determination.UNABLE_TO_DETERMINE
    occupant_count: int | None = None

    @property
    def first_seen_frame(self) -> int:
        if not self.points:
            raise ValueError(f"Track {self.track_id} has no points")
        return self.points[0].frame_index

    @property
    def last_seen_frame(self) -> int:
        if not self.points:
            raise ValueError(f"Track {self.track_id} has no points")
        return self.points[-1].frame_index

    @property
    def duration_s(self) -> float:
        if len(self.points) < 2:
            return 0.0
        return self.points[-1].timestamp_s - self.points[0].timestamp_s

    @property
    def latest(self) -> TrackPoint | None:
        return self.points[-1] if self.points else None

    def add_point(self, point: TrackPoint, observed_class: VehicleClass | None = None) -> None:
        self.points.append(point)
        if observed_class is not None:
            self.class_votes[observed_class] = self.class_votes.get(observed_class, 0) + 1
            self.vehicle_class = max(self.class_votes.items(), key=lambda item: item[1])[0]

    def path(self) -> list[Point]:
        """Ground-contact positions, in time order."""
        return [point.position for point in self.points]

    def displacement_px(self) -> float:
        """Straight-line distance between the first and last observation."""
        if len(self.points) < 2:
            return 0.0
        return self.points[0].position.distance_to(self.points[-1].position)

    def path_length_px(self) -> float:
        """Distance actually travelled along the path."""
        positions = self.path()
        return sum(
            positions[index].distance_to(positions[index + 1]) for index in range(len(positions) - 1)
        )


def bearing_degrees(origin: Point, destination: Point) -> float:
    """Bearing from ``origin`` to ``destination``, clockwise from image-up.

    Image y grows downward, so "up" in the frame is ``-y``. Negating dy before
    the atan2 call puts the result on the same compass convention used for GPS
    headings, which lets the alert engine reuse one comparison function.

    Returns 0.0 for coincident points, where a bearing is undefined.
    """
    dx = destination.x - origin.x
    dy = -(destination.y - origin.y)
    if dx == 0.0 and dy == 0.0:
        return 0.0
    return normalize_bearing(math.degrees(math.atan2(dx, dy)))


def angular_difference(first_deg: float, second_deg: float) -> float:
    """Smallest absolute angle between two bearings, in ``[0, 180]``.

    Used for wrong-way detection (difference near 180 degrees) and for deciding
    whether a risk zone lies ahead of a driver rather than behind them.
    """
    delta = abs(first_deg - second_deg) % 360.0
    return delta if delta <= 180.0 else 360.0 - delta


def average_bearing(bearings: Iterable[float]) -> float | None:
    """Circular mean of bearings.

    A plain arithmetic mean is wrong on a circle: 350 and 10 degrees average to
    180 rather than 0. Averaging unit vectors avoids that.

    Returns ``None`` for an empty input, or when the bearings cancel out and no
    dominant direction exists.
    """
    values: Sequence[float] = list(bearings)
    if not values:
        return None

    sin_sum = sum(math.sin(math.radians(value)) for value in values)
    cos_sum = sum(math.cos(math.radians(value)) for value in values)
    if abs(sin_sum) < 1e-9 and abs(cos_sum) < 1e-9:
        return None
    return normalize_bearing(math.degrees(math.atan2(sin_sum, cos_sum)))
