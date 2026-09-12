"""Scripted detector: replays predetermined detections.

Two jobs, which is why it lives in the product rather than in a test folder:

1. **Verification.** It lets the tracking, motion, safety and conflict stages be
   exercised against motion with a known ground truth, so a failure there is
   distinguishable from a detector failure.
2. **Demo mode.** It is the simulator behind demo mode. Everything it produces
   is tagged ``DataOrigin.DEMO`` by the caller, and the dashboard labels it.

It is never a fallback for a missing model. When real weights are unavailable
the pipeline raises; quietly substituting synthetic detections for real ones
would put invented traffic on an operator's screen.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from trajyx_cv.detection.base import DetectorInfo
from trajyx_cv.types import BoundingBox, Detection, FrameMeta
from trajyx_shared.domain import VehicleClass


@dataclass(slots=True)
class ScriptedActor:
    """One object moving through the scene."""

    vehicle_class: VehicleClass
    start_x: float
    start_y: float
    velocity_x: float
    """Pixels per second."""
    velocity_y: float = 0.0
    width: float = 70.0
    height: float = 34.0
    confidence: float = 0.88
    appear_s: float = 0.0
    disappear_s: float = 1e9

    #: Deceleration in px/s^2 applied after `brake_at_s`. Produces hard braking
    #: and, with a follower behind, a near miss.
    brake_at_s: float | None = None
    brake_rate: float = 260.0

    #: Frames where the detector "loses" the object, to exercise the tracker's
    #: low-confidence rescue path.
    occluded_between_s: tuple[float, float] | None = None

    def position_at(self, t: float) -> tuple[float, float]:
        elapsed = max(0.0, t - self.appear_s)
        x = self.start_x + self.velocity_x * elapsed
        y = self.start_y + self.velocity_y * elapsed

        if self.brake_at_s is not None and t > self.brake_at_s:
            braking = t - self.brake_at_s
            # Distance lost to braking, never reversing past a standstill.
            stop_time = abs(self.velocity_x) / self.brake_rate if self.brake_rate else 0.0
            effective = min(braking, stop_time)
            lost = 0.5 * self.brake_rate * effective**2
            x -= math.copysign(lost, self.velocity_x)
        return x, y

    def confidence_at(self, t: float) -> float:
        if self.occluded_between_s is not None:
            start, end = self.occluded_between_s
            if start <= t <= end:
                # Low but non-zero: exactly the case ByteTrack's second pass is for.
                return 0.28
        return self.confidence

    def visible_at(self, t: float) -> bool:
        return self.appear_s <= t <= self.disappear_s


@dataclass
class ScriptedDetector:
    """Emits the detections described by its actors."""

    actors: list[ScriptedActor] = field(default_factory=list)
    version: str = "scripted-1.0"
    jitter_px: float = 1.5
    """Box noise, so the motion module's smoothing is actually exercised."""

    seed: int = 7

    def __post_init__(self) -> None:
        self._info = DetectorInfo(
            name="scripted",
            version=self.version,
            classes=tuple(sorted({actor.vehicle_class for actor in self.actors}, key=lambda c: c.value)),
            device="cpu",
        )
        self.last_inference_ms: float = 0.0
        self.unmapped_labels: dict[str, int] = {}

    @property
    def info(self) -> DetectorInfo:
        return self._info

    def warmup(self) -> None:
        return None

    def detect(self, frame: np.ndarray, meta: FrameMeta) -> list[Detection]:
        del frame
        rng = np.random.default_rng(self.seed + meta.index)
        detections: list[Detection] = []

        for actor in self.actors:
            if not actor.visible_at(meta.timestamp_s):
                continue

            x, y = actor.position_at(meta.timestamp_s)
            if self.jitter_px > 0:
                x += float(rng.normal(0.0, self.jitter_px))
                y += float(rng.normal(0.0, self.jitter_px))

            # Drop anything fully outside the frame.
            if x + actor.width < 0 or x > meta.width or y + actor.height < 0 or y > meta.height:
                continue

            box = BoundingBox(
                x1=x, y1=y, x2=x + actor.width, y2=y + actor.height
            ).clip_to(meta.width, meta.height)
            if box.area <= 1.0:
                continue

            detections.append(
                Detection(
                    vehicle_class=actor.vehicle_class,
                    confidence=actor.confidence_at(meta.timestamp_s),
                    box=box,
                    frame_index=meta.index,
                    timestamp_s=meta.timestamp_s,
                    raw_class_name=f"scripted:{actor.vehicle_class.value}",
                )
            )
        return detections

    def detect_batch(self, frames, metas) -> list[list[Detection]]:  # noqa: ANN001
        return [self.detect(frame, meta) for frame, meta in zip(frames, metas, strict=True)]


def junction_scenario() -> ScriptedDetector:
    """A scene containing every behaviour the safety engine should catch.

    Lane 0 (upper) runs east at heading 90; lane 1 (lower) runs west at 270.

    - two normal eastbound cars
    - one normal westbound truck
    - one car travelling east in the westbound lane  -> WRONG_WAY
    - a leader that brakes hard with a follower closing -> HARD_BRAKING + NEAR_MISS
    - a pedestrian crossing into traffic -> PEDESTRIAN interaction
    - one car briefly occluded -> tracker identity must survive
    """
    return ScriptedDetector(
        actors=[
            # Normal eastbound.
            ScriptedActor(VehicleClass.CAR, -90, 250, 95, width=76, height=34),
            ScriptedActor(
                VehicleClass.CAR, -320, 256, 78, width=80, height=36,
                occluded_between_s=(4.0, 5.2),
            ),
            # Normal westbound.
            ScriptedActor(VehicleClass.TRUCK, 1020, 425, -88, width=104, height=46),
            # WRONG WAY: eastbound in the westbound lane.
            ScriptedActor(VehicleClass.CAR, -200, 452, 105, width=78, height=36),
            # Leader brakes hard at 5.5s; follower closes on it.
            ScriptedActor(
                VehicleClass.CAR, 120, 300, 70, width=78, height=34, brake_at_s=5.5, brake_rate=300
            ),
            ScriptedActor(VehicleClass.MOTORCYCLE, -95, 306, 96, width=38, height=30),
            # Pedestrian crossing from the verge into the road after 6s.
            ScriptedActor(
                VehicleClass.PEDESTRIAN, 520, 200, 0.0, velocity_y=34,
                width=18, height=46, appear_s=6.0, confidence=0.72,
            ),
        ]
    )
