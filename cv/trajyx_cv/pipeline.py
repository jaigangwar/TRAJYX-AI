"""The analysis pipeline: video in, safety intelligence out.

    decode -> detect -> track -> motion -> safety detectors
                                        -> pairwise conflicts -> near misses
                                        -> risk inputs

One pass over the video. Detection and tracking run per frame; motion,
detectors and conflict analysis run once at the end over complete tracks,
because they all need a track's full history to say anything reliable.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from trajyx_cv.detection.base import Detector
from trajyx_cv.interactions.conflict import Interaction, NearMiss, analyse_all
from trajyx_cv.trajectory.motion import Calibration, MotionSample, apply_to_track
from trajyx_cv.types import Detection, Track
from trajyx_cv.video.reader import AnnotatedWriter, VideoInfo, probe, read_frames
from trajyx_cv.violations.detectors import (
    Availability,
    CameraContext,
    DetectorResult,
    Finding,
    run_all,
)
from trajyx_shared.domain import VehicleClass

log = logging.getLogger(__name__)

#: Class colours for annotation, BGR. Vulnerable road users are warm so they
#: stand out; motorised traffic is cool.
CLASS_COLOURS: dict[VehicleClass, tuple[int, int, int]] = {
    VehicleClass.CAR: (161, 184, 20),
    VehicleClass.MOTORCYCLE: (58, 131, 232),
    VehicleClass.SCOOTER: (58, 160, 232),
    VehicleClass.BUS: (200, 150, 40),
    VehicleClass.TRUCK: (190, 120, 60),
    VehicleClass.AUTO_RICKSHAW: (60, 200, 217),
    VehicleClass.VAN: (170, 170, 50),
    VehicleClass.BICYCLE: (110, 200, 110),
    VehicleClass.PEDESTRIAN: (77, 72, 229),
}
DEFAULT_COLOUR = (180, 180, 180)


@dataclass
class PipelineProgress:
    frames_processed: int = 0
    frames_total: int = 0
    detections: int = 0
    active_tracks: int = 0
    stage: str = "queued"

    @property
    def percent(self) -> float:
        if self.frames_total <= 0:
            return 0.0
        return round(100.0 * self.frames_processed / self.frames_total, 1)


@dataclass
class AnalysisResult:
    video: VideoInfo
    frame_stride: int
    frames_processed: int

    tracks: list[Track] = field(default_factory=list)
    motion: dict[int, list[MotionSample]] = field(default_factory=dict)
    detector_results: dict[int, list[DetectorResult]] = field(default_factory=dict)
    interactions: list[Interaction] = field(default_factory=list)
    near_misses: list[NearMiss] = field(default_factory=list)

    detection_count: int = 0
    class_counts: dict[VehicleClass, int] = field(default_factory=dict)
    unmapped_labels: dict[str, int] = field(default_factory=dict)

    annotated_path: Path | None = None
    detector_name: str = ""
    detector_version: str = ""
    tracker_name: str = ""

    inference_ms_per_frame: float | None = None
    wall_seconds: float = 0.0

    @property
    def vehicle_count(self) -> int:
        """Unique tracked vehicles, not detections.

        Counting detections would multiply every vehicle by the number of
        frames it appears in, which is how traffic counts get inflated tenfold.
        """
        return sum(
            1 for track in self.tracks if track.vehicle_class is not VehicleClass.PEDESTRIAN
        )

    @property
    def pedestrian_count(self) -> int:
        return sum(
            1 for track in self.tracks if track.vehicle_class is VehicleClass.PEDESTRIAN
        )

    @property
    def findings(self) -> list[Finding]:
        return [
            finding
            for results in self.detector_results.values()
            for result in results
            if result.availability is Availability.AVAILABLE
            for finding in result.findings
        ]

    @property
    def unavailable_checks(self) -> dict[str, str]:
        """Checks that could not run, and why. Surfaced to operators verbatim."""
        reasons: dict[str, str] = {}
        for results in self.detector_results.values():
            for result in results:
                if result.availability is Availability.UNAVAILABLE and result.unavailable_reason:
                    reasons[result.name] = result.unavailable_reason
        return reasons

    @property
    def minimum_ttc_s(self) -> float | None:
        values = [
            interaction.estimated_ttc_s
            for interaction in self.interactions
            if interaction.estimated_ttc_s is not None
        ]
        return round(min(values), 2) if values else None

    @property
    def mean_interaction_score(self) -> float | None:
        if not self.interactions:
            return None
        return round(
            sum(item.interaction_score for item in self.interactions) / len(self.interactions), 1
        )


ProgressCallback = Callable[[PipelineProgress], None]


def analyse_video(
    path: Path,
    detector: Detector,
    *,
    context: CameraContext | None = None,
    stride: int = 2,
    max_frames: int | None = None,
    annotated_output: Path | None = None,
    on_progress: ProgressCallback | None = None,
) -> AnalysisResult:
    """Run the full pipeline over one video."""
    from trajyx_cv.tracking.bytetrack import tracker_for

    started = time.perf_counter()
    context = context or CameraContext()
    info = probe(path)

    # Calibration lives on the context; the motion module needs frame height to
    # apply its perspective correction.
    calibration = context.calibration
    if calibration is not None and calibration.frame_height <= 0:
        calibration = Calibration(
            metres_per_pixel_at_reference=calibration.metres_per_pixel_at_reference,
            reference_y=calibration.reference_y,
            frame_height=info.height,
            depth_factor=calibration.depth_factor,
        )

    tracker = tracker_for(info.frame_rate, stride)
    progress = PipelineProgress(
        frames_total=(min(info.frame_count, (max_frames or 10**9) * stride) // max(1, stride)),
        stage="detecting",
    )

    writer: AnnotatedWriter | None = None
    if annotated_output is not None:
        writer = AnnotatedWriter(
            annotated_output, info.width, info.height, info.frame_rate / max(1, stride)
        )

    detection_count = 0
    class_counts: dict[VehicleClass, int] = {}
    inference_samples: list[float] = []

    try:
        detector.warmup()
        for frame, meta in read_frames(path, stride=stride, max_frames=max_frames):
            detections: list[Detection] = detector.detect(frame, meta)
            detection_count += len(detections)
            for detection in detections:
                class_counts[detection.vehicle_class] = (
                    class_counts.get(detection.vehicle_class, 0) + 1
                )

            active = tracker.update(detections, meta)

            latency = getattr(detector, "last_inference_ms", None)
            if latency is not None:
                inference_samples.append(latency)

            if writer is not None:
                writer.write(annotate(frame, active))

            progress.frames_processed += 1
            progress.detections = detection_count
            progress.active_tracks = len(active)
            if on_progress is not None and progress.frames_processed % 10 == 0:
                on_progress(progress)
    finally:
        if writer is not None:
            writer.close()

    progress.stage = "analysing"
    if on_progress is not None:
        on_progress(progress)

    tracks = tracker.finalize()

    # Motion first: every downstream stage reads speed and heading from it.
    motion: dict[int, list[MotionSample]] = {}
    for track in tracks:
        motion[track.track_id] = apply_to_track(track, calibration)

    effective_context = CameraContext(
        calibration=calibration,
        stop_line=context.stop_line,
        lane_directions=context.lane_directions,
        signal_state=context.signal_state,
        speed_limit_kmh=context.speed_limit_kmh,
        frame_width=info.width,
        frame_height=info.height,
    )

    detector_results = {
        track.track_id: run_all(track, motion[track.track_id], effective_context)
        for track in tracks
    }

    interactions, near_misses = analyse_all(tracks, motion, calibration)

    progress.stage = "complete"
    if on_progress is not None:
        on_progress(progress)

    return AnalysisResult(
        video=info,
        frame_stride=stride,
        frames_processed=progress.frames_processed,
        tracks=tracks,
        motion=motion,
        detector_results=detector_results,
        interactions=interactions,
        near_misses=near_misses,
        detection_count=detection_count,
        class_counts=class_counts,
        unmapped_labels=dict(getattr(detector, "unmapped_labels", {})),
        annotated_path=annotated_output,
        detector_name=detector.info.name,
        detector_version=detector.info.version,
        tracker_name=tracker.info.name,
        inference_ms_per_frame=(
            round(sum(inference_samples) / len(inference_samples), 1) if inference_samples else None
        ),
        wall_seconds=round(time.perf_counter() - started, 2),
    )


def annotate(frame: np.ndarray, tracks: list[Track], trail_length: int = 24) -> np.ndarray:
    """Draw boxes, track ids and trajectory trails.

    Deliberately restrained: 1px boxes, a thin trail, small labels. A heavily
    stylised overlay makes the underlying detection harder to judge, and this
    output is evidence.
    """
    canvas = frame.copy()

    for track in tracks:
        latest = track.latest
        if latest is None:
            continue

        colour = CLASS_COLOURS.get(track.vehicle_class, DEFAULT_COLOUR)
        x1, y1, x2, y2 = (int(value) for value in latest.box.as_xyxy())
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 1, cv2.LINE_AA)

        # Trajectory trail, fading with age.
        trail = track.points[-trail_length:]
        for index in range(1, len(trail)):
            start = trail[index - 1].position
            end = trail[index].position
            weight = index / len(trail)
            faded = tuple(int(channel * (0.35 + 0.65 * weight)) for channel in colour)
            cv2.line(
                canvas,
                (int(start.x), int(start.y)),
                (int(end.x), int(end.y)),
                faded,
                1,
                cv2.LINE_AA,
            )

        label = f"{track.vehicle_class.value[:4]} #{track.track_id}"
        if latest.speed_kmh is not None:
            label += f" ~{latest.speed_kmh:.0f}km/h"  # ~ marks it as an estimate

        (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
        cv2.rectangle(
            canvas, (x1, y1 - text_height - 5), (x1 + text_width + 4, y1), colour, -1
        )
        cv2.putText(
            canvas,
            label,
            (x1 + 2, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.35,
            (15, 20, 25),
            1,
            cv2.LINE_AA,
        )

    return canvas
