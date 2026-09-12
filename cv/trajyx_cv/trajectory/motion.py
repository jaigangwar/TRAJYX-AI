"""Trajectory smoothing, speed and heading estimation.

Speed is the value most easily faked and most easily believed, so it is gated:
without camera calibration this module returns ``None`` for speed, never a
pixel-based number dressed up as km/h.

Acceleration is gated a second way, by physics. Differentiating a jittery
position series produces enormous spurious accelerations — 30 m/s² and beyond,
which is three times what any road vehicle can do. Those are measurement
noise, not behaviour, so speed is smoothed before differentiation and
implausible results are discarded rather than reported as hard braking.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from trajyx_cv.types import Point, Track, average_bearing, bearing_degrees

#: Minimum pixel displacement before a heading is considered meaningful. Below
#: this, the "direction" is box jitter, and a jittered heading would produce
#: false wrong-way events.
MIN_HEADING_DISPLACEMENT_PX = 8.0

#: Frames either side used to smooth a heading estimate.
HEADING_WINDOW = 3

#: Frames either side used to smooth speed before differentiating.
SPEED_WINDOW = 5

#: Largest acceleration or deceleration treated as real, in m/s². Emergency
#: braking peaks around 8-9 m/s² (0.9 g) on dry asphalt and hard acceleration
#: around 5 m/s² for a passenger car. Anything past this is tracking noise, so
#: it is dropped rather than surfaced as a violation.
MAX_PLAUSIBLE_ACCELERATION_MS2 = 10.0

#: Speed above this is treated as a tracking error rather than a vehicle.
MAX_PLAUSIBLE_SPEED_KMH = 200.0


@dataclass(frozen=True, slots=True)
class Calibration:
    """Image-to-ground scale for one camera.

    A single scalar is an approximation: a road-facing camera compresses
    distance with depth, so metres-per-pixel at the top of the frame is not
    what it is at the bottom. `depth_factor` applies a linear correction with
    image row, which is crude but much better than ignoring perspective.
    Anything derived from this is reported as ESTIMATED.
    """

    metres_per_pixel_at_reference: float
    reference_y: float
    frame_height: int
    depth_factor: float = 0.6

    def metres_per_pixel_at(self, y: float) -> float:
        """Scale at image row `y`.

        Rows above the reference (further away) get more metres per pixel;
        rows below get fewer. Clamped so a near-zero or runaway scale cannot
        produce an absurd speed.
        """
        if self.frame_height <= 0:
            return self.metres_per_pixel_at_reference

        offset = (y - self.reference_y) / max(1.0, self.frame_height)
        scale = 1.0 - self.depth_factor * offset
        return self.metres_per_pixel_at_reference * max(0.25, min(4.0, scale))


@dataclass(frozen=True, slots=True)
class MotionSample:
    """Motion state at one track point."""

    frame_index: int
    timestamp_s: float
    position: Point
    heading_deg: float | None
    speed_kmh: float | None
    """``None`` when the camera is uncalibrated. Never a pixel figure."""
    speed_px_per_s: float
    acceleration_kmh_s: float | None
    """``None`` when uncalibrated, or when the value was physically implausible
    and therefore attributed to tracking noise."""


def smooth_positions(track: Track, window: int = 3) -> list[Point]:
    """Moving-average smoothing of ground-contact positions.

    Box coordinates jitter by a few pixels per frame even for a stationary
    vehicle. Unsmoothed, that jitter becomes fake acceleration and fake
    heading changes, which then become fake hard-braking and wrong-way events.
    """
    positions = track.path()
    if len(positions) <= 2 or window <= 1:
        return positions

    half = window // 2
    smoothed: list[Point] = []
    for index in range(len(positions)):
        start = max(0, index - half)
        end = min(len(positions), index + half + 1)
        chunk = positions[start:end]
        smoothed.append(
            Point(
                x=sum(point.x for point in chunk) / len(chunk),
                y=sum(point.y for point in chunk) / len(chunk),
            )
        )
    return smoothed


def _smooth_series(values: list[float], window: int) -> list[float]:
    if len(values) <= 2 or window <= 1:
        return values
    half = window // 2
    return [
        statistics.fmean(values[max(0, i - half) : min(len(values), i + half + 1)])
        for i in range(len(values))
    ]


def representative_width(track: Track) -> float:
    """Median box width across the track.

    The per-frame width is unreliable: a vehicle entering or leaving the frame
    has its box clipped, so using the instantaneous width made a 78px car
    measure 11px and turned normal travel into a "dangerous lane change".
    """
    widths = [point.box.width for point in track.points if point.box.width > 0]
    return statistics.median(widths) if widths else 1.0


def analyse(track: Track, calibration: Calibration | None = None) -> list[MotionSample]:
    """Per-point motion for a track."""
    if len(track.points) < 2:
        return []

    positions = smooth_positions(track)
    count = len(track.points)

    # --- pixel speed, by central difference where possible ------------------
    raw_speed_px: list[float] = []
    for index in range(count):
        previous = max(0, index - 1)
        following = min(count - 1, index + 1)
        dt = track.points[following].timestamp_s - track.points[previous].timestamp_s
        distance = positions[previous].distance_to(positions[following])
        raw_speed_px.append(distance / dt if dt > 1e-6 else 0.0)

    speed_px = _smooth_series(raw_speed_px, SPEED_WINDOW)

    # --- convert to km/h, only when calibrated ------------------------------
    speed_kmh: list[float | None] = []
    for index in range(count):
        if calibration is None:
            speed_kmh.append(None)
            continue
        scale = calibration.metres_per_pixel_at(positions[index].y)
        value = speed_px[index] * scale * 3.6
        speed_kmh.append(value if value <= MAX_PLAUSIBLE_SPEED_KMH else None)

    # Smooth again in km/h so the perspective correction does not reintroduce
    # steps as a vehicle moves through the frame.
    known = [value for value in speed_kmh if value is not None]
    if known and len(known) == count:
        smoothed_kmh: list[float | None] = list(_smooth_series([v for v in speed_kmh if v is not None], SPEED_WINDOW))  # type: ignore[arg-type]
    else:
        smoothed_kmh = speed_kmh

    samples: list[MotionSample] = []
    for index in range(count):
        point = track.points[index]

        # --- acceleration, central difference, plausibility-gated -----------
        acceleration: float | None = None
        if calibration is not None and 0 < index < count - 1:
            before = smoothed_kmh[index - 1]
            after = smoothed_kmh[index + 1]
            dt = track.points[index + 1].timestamp_s - track.points[index - 1].timestamp_s
            if before is not None and after is not None and dt > 1e-6:
                candidate = (after - before) / dt
                # Discard the physically impossible: it is tracking noise, and
                # reporting it would manufacture braking violations.
                if abs(candidate / 3.6) <= MAX_PLAUSIBLE_ACCELERATION_MS2:
                    acceleration = candidate

        samples.append(
            MotionSample(
                frame_index=point.frame_index,
                timestamp_s=point.timestamp_s,
                position=positions[index],
                heading_deg=_heading_at(positions, index),
                speed_kmh=smoothed_kmh[index],
                speed_px_per_s=speed_px[index],
                acceleration_kmh_s=acceleration,
            )
        )

    return samples


def _heading_at(positions: list[Point], index: int) -> float | None:
    """Smoothed heading, or None when the track has not moved enough."""
    start = max(0, index - HEADING_WINDOW)
    end = min(len(positions) - 1, index + HEADING_WINDOW)
    if end <= start:
        return None

    if positions[start].distance_to(positions[end]) < MIN_HEADING_DISPLACEMENT_PX:
        return None

    bearings = [
        bearing_degrees(positions[step], positions[step + 1])
        for step in range(start, end)
        if positions[step].distance_to(positions[step + 1]) > 1.0
    ]
    return average_bearing(bearings) if bearings else None


def dominant_heading(samples: list[MotionSample]) -> float | None:
    """The track's overall direction of travel."""
    bearings = [sample.heading_deg for sample in samples if sample.heading_deg is not None]
    return average_bearing(bearings) if bearings else None


def mean_position(samples: list[MotionSample]) -> Point | None:
    """Average position, used to decide which lane a track occupies."""
    if not samples:
        return None
    return Point(
        x=statistics.fmean(sample.position.x for sample in samples),
        y=statistics.fmean(sample.position.y for sample in samples),
    )


def apply_to_track(track: Track, calibration: Calibration | None = None) -> list[MotionSample]:
    """Analyse a track and write the results back onto its points."""
    samples = analyse(track, calibration)
    for point, sample in zip(track.points, samples, strict=True):
        point.speed_kmh = sample.speed_kmh
        point.heading_deg = sample.heading_deg
    return samples
