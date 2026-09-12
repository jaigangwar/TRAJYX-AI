"""Vehicle interaction, time-to-collision and near-miss detection.

Near misses matter more than crashes for prediction: they are far more
frequent, they share the same causes, and a road segment producing near misses
is telling you where the next crash will be. This module finds them.

Every number here is an estimate from image-space geometry. TTC in particular
is labelled as estimated everywhere it surfaces, and is only expressed in
seconds at all — pixel-based TTC is still a time, because the pixel scale
cancels between distance and closing speed.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from trajyx_cv.trajectory.motion import Calibration, MotionSample
from trajyx_cv.types import Point, Track
from trajyx_shared.domain import Severity, TtcBand, VehicleClass, ttc_band_from_seconds

#: Pairs further apart than this (in vehicle widths) are not worth analysing.
#: Keeps the pairwise scan from being O(n^2) over the whole frame.
MAX_INTERACTION_WIDTHS = 6.0

#: Below this closing speed the pair is not converging meaningfully.
MIN_CLOSING_SPEED_PX_S = 5.0

#: TTC at or below this is a near miss.
NEAR_MISS_TTC_S = 2.0

#: A gap below this many vehicle widths counts as a conflict even without
#: converging headings: two vehicles this close are interacting whatever their
#: paths are doing.
CONFLICT_GAP_WIDTHS = 0.6

#: Frames either side used to smooth the gap series before differentiating.
GAP_SMOOTHING_WINDOW = 5

#: A near miss must persist at least this many consecutive analysed frames.
#: One frame is noise; a real conflict develops over several.
MIN_NEAR_MISS_FRAMES = 2

#: Vulnerable road users get a wider conflict envelope.
VULNERABLE = frozenset({VehicleClass.PEDESTRIAN, VehicleClass.BICYCLE, VehicleClass.MOTORCYCLE,
                        VehicleClass.SCOOTER})
VULNERABLE_MULTIPLIER = 1.8


@dataclass(frozen=True, slots=True)
class Interaction:
    """Pairwise state between two tracks at one instant."""

    frame_index: int
    timestamp_s: float
    track_a: int
    track_b: int
    class_a: VehicleClass
    class_b: VehicleClass

    gap_px: float
    """Shortest distance between the two boxes. 0 when they overlap."""

    closing_speed_px_s: float
    """Rate at which the gap is shrinking. Negative means separating."""

    estimated_ttc_s: float | None
    """Gap divided by closing speed. ``None`` when not converging."""

    ttc_band: TtcBand | None
    paths_converge: bool
    relative_speed_px_s: float
    interaction_score: float
    """0-100. Combines proximity, closing rate and vulnerability."""

    gap_m: float | None = None
    """Gap in metres, only when the camera is calibrated."""


@dataclass(frozen=True, slots=True)
class NearMiss:
    """A conflict that did not become a collision."""

    frame_index: int
    timestamp_s: float
    track_ids: tuple[int, int]
    classes: tuple[VehicleClass, VehicleClass]
    estimated_ttc_s: float | None
    ttc_band: TtcBand | None
    gap_px: float
    gap_m: float | None
    closing_speed_px_s: float
    interaction_score: float
    risk_factors: tuple[str, ...] = field(default_factory=tuple)
    severity: Severity = Severity.MAJOR


def _sample_at(samples: list[MotionSample], frame_index: int) -> MotionSample | None:
    for sample in samples:
        if sample.frame_index == frame_index:
            return sample
    return None


def _box_gap(track_a: Track, track_b: Track, frame_index: int) -> tuple[float, float] | None:
    """(gap in px, mean vehicle width) at a shared frame, or None."""
    point_a = next((p for p in track_a.points if p.frame_index == frame_index), None)
    point_b = next((p for p in track_b.points if p.frame_index == frame_index), None)
    if point_a is None or point_b is None:
        return None

    first, second = point_a.box, point_b.box
    dx = max(0.0, max(first.x1 - second.x2, second.x1 - first.x2))
    dy = max(0.0, max(first.y1 - second.y2, second.y1 - first.y2))
    gap = math.hypot(dx, dy)
    mean_width = (first.width + second.width) / 2.0
    return gap, max(1.0, mean_width)


def _paths_converge(a: MotionSample, b: MotionSample) -> bool:
    """Whether the two headings point into each other's path.

    Cheap proxy for trajectory intersection: if the vector between them has a
    positive component along A's heading and a negative one along B's, they are
    closing on each other rather than travelling in parallel.
    """
    if a.heading_deg is None or b.heading_deg is None:
        return False

    def forward(heading: float) -> tuple[float, float]:
        radians = math.radians(heading)
        return math.sin(radians), -math.cos(radians)

    ax, ay = forward(a.heading_deg)
    bx, by = forward(b.heading_deg)

    separation = (b.position.x - a.position.x, b.position.y - a.position.y)
    magnitude = math.hypot(*separation)
    if magnitude < 1e-6:
        return True

    unit = (separation[0] / magnitude, separation[1] / magnitude)
    a_towards_b = ax * unit[0] + ay * unit[1]
    b_towards_a = bx * -unit[0] + by * -unit[1]
    return a_towards_b > 0.2 and b_towards_a > 0.2


def analyse_pair(
    track_a: Track,
    track_b: Track,
    samples_a: list[MotionSample],
    samples_b: list[MotionSample],
    calibration: Calibration | None = None,
) -> list[Interaction]:
    """Interaction state for every frame the two tracks share.

    The gap series is smoothed before differentiation, for the same reason
    speed is: box jitter of a couple of pixels per frame turns a constant
    following distance into a wildly oscillating closing speed, and a single
    negative spike becomes a fabricated sub-second time-to-collision.
    """
    shared = sorted(
        {p.frame_index for p in track_a.points} & {p.frame_index for p in track_b.points}
    )
    if len(shared) < 3:
        return []

    # --- pass 1: measure the raw geometry per shared frame -------------------
    frames: list[int] = []
    times: list[float] = []
    gaps: list[float] = []
    widths: list[float] = []
    pairs: list[tuple[MotionSample, MotionSample]] = []

    for frame_index in shared:
        measured = _box_gap(track_a, track_b, frame_index)
        sample_a = _sample_at(samples_a, frame_index)
        sample_b = _sample_at(samples_b, frame_index)
        if measured is None or sample_a is None or sample_b is None:
            continue

        gap, mean_width = measured
        frames.append(frame_index)
        times.append(sample_a.timestamp_s)
        gaps.append(gap)
        widths.append(mean_width)
        pairs.append((sample_a, sample_b))

    if len(gaps) < 3:
        return []

    smoothed = _smooth(gaps, GAP_SMOOTHING_WINDOW)

    # --- pass 2: derive closing speed and TTC from the smoothed series ------
    interactions: list[Interaction] = []
    for index in range(len(smoothed)):
        gap = smoothed[index]
        mean_width = widths[index]
        sample_a, sample_b = pairs[index]

        if gap > mean_width * MAX_INTERACTION_WIDTHS:
            continue

        # Central difference, so closing speed is not biased by which side of
        # the sample the neighbour happens to be on.
        low = max(0, index - 1)
        high = min(len(smoothed) - 1, index + 1)
        dt = times[high] - times[low]
        closing = (smoothed[low] - smoothed[high]) / dt if dt > 1e-6 else 0.0

        converge = _paths_converge(sample_a, sample_b)

        ttc: float | None = None
        if closing > MIN_CLOSING_SPEED_PX_S:
            # Converging paths, or a gap already small enough that closing at
            # all is a conflict. Two vehicles in adjacent lanes travelling
            # parallel are not on a collision course, however close they look
            # in frame, and treating them as one floods the near-miss list.
            if converge or gap < mean_width * CONFLICT_GAP_WIDTHS:
                ttc = gap / closing

        relative = abs(sample_a.speed_px_per_s - sample_b.speed_px_per_s)

        gap_m: float | None = None
        if calibration is not None:
            mean_y = (sample_a.position.y + sample_b.position.y) / 2.0
            gap_m = gap * calibration.metres_per_pixel_at(mean_y)

        interactions.append(
            Interaction(
                frame_index=frames[index],
                timestamp_s=times[index],
                track_a=track_a.track_id,
                track_b=track_b.track_id,
                class_a=track_a.vehicle_class,
                class_b=track_b.vehicle_class,
                gap_px=gap,
                closing_speed_px_s=closing,
                estimated_ttc_s=ttc,
                ttc_band=ttc_band_from_seconds(ttc),
                paths_converge=converge,
                relative_speed_px_s=relative,
                interaction_score=_score(
                    gap,
                    mean_width,
                    closing,
                    ttc,
                    converge,
                    track_a.vehicle_class,
                    track_b.vehicle_class,
                ),
                gap_m=gap_m,
            )
        )

    return interactions


def _smooth(values: list[float], window: int) -> list[float]:
    if len(values) <= 2 or window <= 1:
        return values
    half = window // 2
    return [
        statistics.fmean(values[max(0, i - half) : min(len(values), i + half + 1)])
        for i in range(len(values))
    ]


def _score(
    gap: float,
    mean_width: float,
    closing: float,
    ttc: float | None,
    converge: bool,
    class_a: VehicleClass,
    class_b: VehicleClass,
) -> float:
    """Interaction score, 0-100.

    Weighted so that time-to-collision dominates: two vehicles 3 metres apart
    and separating is safe, while two vehicles 8 metres apart closing fast is
    not, and only TTC distinguishes them.
    """
    # Proximity: 1.0 when touching, 0 at the analysis cutoff.
    proximity = max(0.0, 1.0 - gap / (mean_width * MAX_INTERACTION_WIDTHS))

    # Urgency from TTC: 1.0 at 0 s, 0 at 5 s.
    urgency = 0.0 if ttc is None else max(0.0, 1.0 - ttc / 5.0)

    # Closing rate, normalised against a brisk 200 px/s.
    approach = min(1.0, max(0.0, closing) / 200.0)

    score = 100.0 * (0.25 * proximity + 0.50 * urgency + 0.15 * approach)
    if converge:
        score += 10.0
    if class_a in VULNERABLE or class_b in VULNERABLE:
        score *= VULNERABLE_MULTIPLIER * 0.6 + 0.4  # 1.48x at most

    return round(min(100.0, score), 1)


def find_near_misses(interactions: list[Interaction]) -> list[NearMiss]:
    """Collapse an interaction series into distinct near-miss events.

    One conflict spans many frames; the peak-severity frame is kept as the
    event so counts reflect conflicts, not frames.
    """
    candidates = [interaction for interaction in interactions if _is_near_miss(interaction)]
    if not candidates:
        return []

    # Group frames into bursts separated by more than a second.
    bursts: list[list[Interaction]] = [[candidates[0]]]
    for interaction in candidates[1:]:
        if interaction.timestamp_s - bursts[-1][-1].timestamp_s <= 1.0:
            bursts[-1].append(interaction)
        else:
            bursts.append([interaction])

    near_misses: list[NearMiss] = []
    for burst in bursts:
        # A single frame is measurement noise, not a conflict.
        if len(burst) < MIN_NEAR_MISS_FRAMES:
            continue
        peak = max(burst, key=lambda item: item.interaction_score)
        near_misses.append(
            NearMiss(
                frame_index=peak.frame_index,
                timestamp_s=peak.timestamp_s,
                track_ids=(peak.track_a, peak.track_b),
                classes=(peak.class_a, peak.class_b),
                estimated_ttc_s=round(peak.estimated_ttc_s, 2) if peak.estimated_ttc_s else None,
                ttc_band=peak.ttc_band,
                gap_px=round(peak.gap_px, 1),
                gap_m=round(peak.gap_m, 2) if peak.gap_m is not None else None,
                closing_speed_px_s=round(peak.closing_speed_px_s, 1),
                interaction_score=peak.interaction_score,
                risk_factors=_factors(peak),
                severity=_severity(peak),
            )
        )
    return near_misses


def _is_near_miss(interaction: Interaction) -> bool:
    # A TTC is only produced for genuinely converging or already-close pairs,
    # so a short one is sufficient on its own.
    if interaction.estimated_ttc_s is not None and interaction.estimated_ttc_s <= NEAR_MISS_TTC_S:
        return True
    # Nearly touching and still closing.
    return interaction.gap_px < 12.0 and interaction.closing_speed_px_s > MIN_CLOSING_SPEED_PX_S


def _factors(interaction: Interaction) -> tuple[str, ...]:
    """Human-readable reasons, shown verbatim to operators and drivers.

    An unexplained risk score is not actionable; these are the explanation.
    """
    factors: list[str] = []
    if interaction.estimated_ttc_s is not None:
        if interaction.estimated_ttc_s < 1.0:
            factors.append("Estimated time to collision under 1 second")
        elif interaction.estimated_ttc_s <= NEAR_MISS_TTC_S:
            factors.append(f"Estimated time to collision {interaction.estimated_ttc_s:.1f} seconds")
    if interaction.gap_m is not None and interaction.gap_m < 2.0:
        factors.append(f"Separation under {interaction.gap_m:.1f} metres")
    elif interaction.gap_px < 10.0:
        factors.append("Vehicles nearly touching in frame")
    if interaction.paths_converge:
        factors.append("Trajectories converging")
    if interaction.closing_speed_px_s > 150.0:
        factors.append("High closing rate")
    if interaction.class_a in VULNERABLE or interaction.class_b in VULNERABLE:
        vulnerable = [
            item.value.lower().replace("_", " ")
            for item in (interaction.class_a, interaction.class_b)
            if item in VULNERABLE
        ]
        factors.append(f"Vulnerable road user involved ({', '.join(vulnerable)})")
    return tuple(factors)


def _severity(interaction: Interaction) -> Severity:
    if interaction.estimated_ttc_s is not None and interaction.estimated_ttc_s < 1.0:
        return Severity.CRITICAL
    if interaction.interaction_score >= 70:
        return Severity.CRITICAL
    if interaction.interaction_score >= 45:
        return Severity.MAJOR
    return Severity.MINOR


def analyse_all(
    tracks: list[Track],
    samples: dict[int, list[MotionSample]],
    calibration: Calibration | None = None,
) -> tuple[list[Interaction], list[NearMiss]]:
    """Analyse every track pair that overlaps in time."""
    interactions: list[Interaction] = []
    near_misses: list[NearMiss] = []

    for index, track_a in enumerate(tracks):
        for track_b in tracks[index + 1 :]:
            # Skip pairs that never co-existed: no shared frame means no
            # interaction, and checking this first avoids the geometry work.
            if track_a.last_seen_frame < track_b.first_seen_frame:
                continue
            if track_b.last_seen_frame < track_a.first_seen_frame:
                continue

            pair = analyse_pair(
                track_a,
                track_b,
                samples.get(track_a.track_id, []),
                samples.get(track_b.track_id, []),
                calibration,
            )
            if not pair:
                continue
            interactions.extend(pair)
            near_misses.extend(find_near_misses(pair))

    return interactions, near_misses


def closest_point_of_approach(a: Point, b: Point) -> float:
    """Straight-line distance. Kept separate so callers read intent."""
    return a.distance_to(b)
