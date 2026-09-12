"""Analysis worker.

Runs the CV pipeline off the request path. Video analysis takes minutes; an
HTTP request must not. Jobs move
``QUEUED -> PROCESSING -> COMPLETED | FAILED`` and progress is written to the
job document so the dashboard can poll it.

The worker runs in-process behind the ``JobQueue`` interface. Because the
routes depend on that interface rather than on this implementation, moving to
Redis + RQ with GPU workers is a change of one binding.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from trajyx_shared.domain import (
    EVENT_CATEGORY,
    DataOrigin,
    EventCategory,
    EventType,
    JobStatus,
    Severity,
)

from app.core.config import Settings
from app.repositories.base import DocumentStore, utc_now
from app.risk.engine import RiskInputs, assess, assessment_to_dict
from app.schemas.events import EventCreate
from app.schemas.jobs import AnalyseRequest
from app.services.event_service import EventService
from app.services.storage import ObjectStorage, processed_video_key

log = structlog.get_logger(__name__)

JOBS = "video_jobs"
ANALYSIS = "video_analysis"
CAMERAS = "cameras"

#: Trajectory points kept per track for the UI overlay. A 10-minute clip can
#: produce thousands per vehicle; the overlay needs tens.
MAX_PATH_POINTS = 60


class JobQueue(abc.ABC):
    """Somewhere to put work that must not block a request."""

    @abc.abstractmethod
    async def enqueue(self, job_id: str, request: AnalyseRequest) -> None: ...

    @abc.abstractmethod
    def pending(self) -> int: ...


class InProcessJobQueue(JobQueue):
    """Runs jobs as asyncio tasks in the API process.

    Adequate for a single-node MVP. Its limits are real and worth stating: work
    is lost on restart, and CPU-bound inference competes with request handling,
    which is why `worker_concurrency` defaults to 1.
    """

    def __init__(self, runner: AnalysisRunner, concurrency: int = 1) -> None:
        self._runner = runner
        self._semaphore = asyncio.Semaphore(max(1, concurrency))
        self._tasks: set[asyncio.Task[None]] = set()

    async def enqueue(self, job_id: str, request: AnalyseRequest) -> None:
        task = asyncio.create_task(self._run(job_id, request))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def pending(self) -> int:
        return sum(1 for task in self._tasks if not task.done())

    async def _run(self, job_id: str, request: AnalyseRequest) -> None:
        async with self._semaphore:
            try:
                await self._runner.run(job_id, request)
            except Exception as error:  # noqa: BLE001 - a worker must never die silently
                log.exception("analysis.worker_failed", job_id=job_id, error=str(error))


class AnalysisRunner:
    """Executes one analysis job end to end."""

    def __init__(self, store: DocumentStore, storage: ObjectStorage, settings: Settings) -> None:
        self._store = store
        self._storage = storage
        self._settings = settings

    async def run(self, job_id: str, request: AnalyseRequest) -> None:
        job = await self._store.get(JOBS, job_id)
        if job is None:
            log.error("analysis.job_missing", job_id=job_id)
            return

        await self._store.update(
            JOBS,
            job_id,
            {
                "status": JobStatus.PROCESSING.value,
                "started_at": utc_now(),
                "progress": {
                    "stage": "starting",
                    "percent": 0.0,
                    "frames_processed": 0,
                    "frames_total": 0,
                    "detections": 0,
                    "active_tracks": 0,
                },
            },
        )

        local_video: Path | None = None
        annotated_local: Path | None = None
        try:
            local_video = await self._storage.local_path(str(job["storage_key"]))
            annotated_local = Path(tempfile.gettempdir()) / f"trajyx-{job_id}-annotated.mp4"

            result = await asyncio.to_thread(
                self._analyse_blocking, job, request, local_video, annotated_local, job_id
            )

            await self._persist(job_id, job, request, result, annotated_local)

        except Exception as error:  # noqa: BLE001 - reported to the operator
            log.exception("analysis.failed", job_id=job_id, error=str(error))
            await self._store.update(
                JOBS,
                job_id,
                {
                    "status": JobStatus.FAILED.value,
                    "completed_at": utc_now(),
                    "error": str(error)[:500],
                    "progress": {
                        "stage": "failed",
                        "percent": 0.0,
                        "frames_processed": 0,
                        "frames_total": 0,
                        "detections": 0,
                        "active_tracks": 0,
                    },
                },
            )
        finally:
            if annotated_local is not None:
                with contextlib.suppress(OSError):
                    annotated_local.unlink(missing_ok=True)

    # ------------------------------------------------------------- blocking

    def _analyse_blocking(
        self,
        job: dict[str, Any],
        request: AnalyseRequest,
        video: Path,
        annotated: Path,
        job_id: str,
    ) -> Any:
        """The CPU-bound part, run in a worker thread."""
        from trajyx_cv.pipeline import analyse_video

        detector = self._build_detector(request)
        context = self._build_context(job, request)
        stride = request.frame_stride or self._settings.frame_stride

        # Progress is written from the thread via a queued coroutine; a direct
        # await is impossible here, so the callback only records the latest
        # snapshot and the loop below persists it.
        latest: dict[str, Any] = {}

        def on_progress(progress: Any) -> None:
            latest.update(
                {
                    "stage": progress.stage,
                    "percent": progress.percent,
                    "frames_processed": progress.frames_processed,
                    "frames_total": progress.frames_total,
                    "detections": progress.detections,
                    "active_tracks": progress.active_tracks,
                }
            )
            # Fire-and-forget write, scheduled on the main loop.
            with contextlib.suppress(RuntimeError):
                asyncio.run_coroutine_threadsafe(
                    self._store.update(JOBS, job_id, {"progress": dict(latest)}),
                    self._loop,
                )

        return analyse_video(
            video,
            detector,
            context=context,
            stride=stride,
            max_frames=request.max_frames,
            annotated_output=annotated,
            on_progress=on_progress,
        )

    _loop: asyncio.AbstractEventLoop

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def _build_detector(self, request: AnalyseRequest) -> Any:
        if request.simulate:
            if not self._settings.demo_mode:
                raise RuntimeError(
                    "Simulated analysis was requested but demo mode is disabled for this "
                    "deployment."
                )
            from trajyx_cv.detection.scripted import junction_scenario

            return junction_scenario()

        # Real detection. A missing model raises rather than falling back to
        # the simulator: synthetic detections presented as measured traffic
        # would be the worst possible failure for this product.
        from trajyx_cv.detection.yolo import YoloDetector

        return YoloDetector(confidence=0.25, device="cpu")

    def _build_context(self, job: dict[str, Any], request: AnalyseRequest) -> Any:
        from trajyx_cv.trajectory.motion import Calibration
        from trajyx_cv.types import Point
        from trajyx_cv.violations.detectors import CameraContext, LaneDirection, StopLineGeometry
        from trajyx_shared.domain import SignalState

        camera = job.get("camera_snapshot") or {}

        calibration = None
        raw_calibration = camera.get("calibration")
        if isinstance(raw_calibration, dict):
            calibration = Calibration(
                metres_per_pixel_at_reference=float(raw_calibration["metres_per_pixel_at_reference"]),
                reference_y=float(raw_calibration["reference_y"]),
                frame_height=int(camera.get("frame_height") or 1080),
            )

        stop_line = None
        raw_stop_line = camera.get("stop_line")
        if isinstance(raw_stop_line, dict):
            stop_line = StopLineGeometry(
                start=Point(float(raw_stop_line["start"]["x"]), float(raw_stop_line["start"]["y"])),
                end=Point(float(raw_stop_line["end"]["x"]), float(raw_stop_line["end"]["y"])),
            )

        lanes = tuple(
            LaneDirection(
                lane_index=int(lane["lane_index"]),
                heading_deg=float(lane["heading_deg"]),
                region_y_min=lane.get("region_y_min"),
                region_y_max=lane.get("region_y_max"),
            )
            for lane in camera.get("lane_directions", [])
            if isinstance(lane, dict)
        )

        signal = SignalState(str(camera.get("signal_state", SignalState.UNKNOWN.value)))

        return CameraContext(
            calibration=calibration,
            stop_line=stop_line,
            lane_directions=lanes,
            signal_state=signal,
            speed_limit_kmh=request.speed_limit_kmh,
        )

    # -------------------------------------------------------------- persist

    async def _persist(
        self,
        job_id: str,
        job: dict[str, Any],
        request: AnalyseRequest,
        result: Any,
        annotated_local: Path,
    ) -> None:
        origin = DataOrigin.DEMO if request.simulate else DataOrigin.MEASURED
        camera_id = job.get("camera_id")

        annotated_key: str | None = None
        if annotated_local.exists() and annotated_local.stat().st_size > 0:
            annotated_key = processed_video_key(job_id)
            with annotated_local.open("rb") as handle:
                await self._storage.put(annotated_key, handle, "video/mp4")

        findings = list(result.findings)
        counts = Counter(finding.event_type.value for finding in findings)
        violations = sum(
            count
            for value, count in counts.items()
            if EVENT_CATEGORY[EventType(value)] is EventCategory.VIOLATION
        )
        behaviour = sum(
            count
            for value, count in counts.items()
            if EVENT_CATEGORY[EventType(value)] is EventCategory.BEHAVIOR
        )

        assessment = assess(
            RiskInputs(
                near_miss_count=len(result.near_misses),
                violation_count=violations,
                wrong_way_count=counts.get(EventType.WRONG_WAY.value, 0),
                hard_braking_count=counts.get(EventType.HARD_BRAKING.value, 0),
                sudden_acceleration_count=counts.get(EventType.SUDDEN_ACCELERATION.value, 0),
                lane_change_count=counts.get(EventType.DANGEROUS_LANE_CHANGE.value, 0),
                pedestrian_conflict_count=counts.get(EventType.PEDESTRIAN_CONFLICT.value, 0),
                vehicle_count=result.vehicle_count,
                pedestrian_count=result.pedestrian_count,
                observation_hours=max(0.001, result.video.duration_s / 3600.0),
                minimum_ttc_s=result.minimum_ttc_s,
                mean_interaction_score=result.mean_interaction_score,
            )
        )
        risk = assessment_to_dict(assessment)

        analysis = await self._store.create(
            ANALYSIS,
            {
                "job_id": job_id,
                "camera_id": camera_id,
                "frame_width": result.video.width,
                "frame_height": result.video.height,
                "frame_rate": result.video.frame_rate,
                "frame_count": result.video.frame_count,
                "duration_s": round(result.video.duration_s, 2),
                "frames_analysed": result.frames_processed,
                "frame_stride": result.frame_stride,
                "detector_name": result.detector_name,
                "detector_version": result.detector_version,
                "tracker_name": result.tracker_name,
                "inference_ms_per_frame": result.inference_ms_per_frame,
                "wall_seconds": result.wall_seconds,
                "detection_count": result.detection_count,
                "vehicle_count": result.vehicle_count,
                "pedestrian_count": result.pedestrian_count,
                "class_counts": {key.value: value for key, value in result.class_counts.items()},
                "unmapped_labels": result.unmapped_labels,
                "track_count": len(result.tracks),
                "tracks": _track_summaries(result),
                "violation_count": violations,
                "behaviour_count": behaviour,
                "near_miss_count": len(result.near_misses),
                "minimum_ttc_s": result.minimum_ttc_s,
                "mean_interaction_score": result.mean_interaction_score,
                "risk_score": risk["risk_score"],
                "risk_level": risk["risk_level"],
                "risk_confidence": risk["confidence"],
                "risk_factors": risk["factors"],
                "top_risk_factors": risk["top_factors"],
                "timeline": _timeline(result),
                "unavailable_checks": [
                    {"name": name, "reason": reason}
                    for name, reason in sorted(result.unavailable_checks.items())
                ],
                "origin": origin.value,
                "annotated_key": annotated_key,
                "created_at": utc_now(),
            },
        )
        analysis_id = str(analysis["id"])

        # Persist the events so they reach the violations and near-miss pages.
        await self._write_events(result, job, analysis_id, origin, assessment)

        await self._store.update(
            JOBS,
            job_id,
            {
                "status": JobStatus.COMPLETED.value,
                "completed_at": utc_now(),
                "annotated_key": annotated_key,
                "analysis_id": analysis_id,
                "origin": origin.value,
                "progress": {
                    "stage": "complete",
                    "percent": 100.0,
                    "frames_processed": result.frames_processed,
                    "frames_total": result.frames_processed,
                    "detections": result.detection_count,
                    "active_tracks": len(result.tracks),
                },
            },
        )

        if camera_id:
            await self._store.update(
                CAMERAS,
                str(camera_id),
                {
                    "current_risk_score": risk["risk_score"],
                    "last_event_at": utc_now(),
                    "last_seen_at": utc_now(),
                },
            )

        log.info(
            "analysis.completed",
            job_id=job_id,
            analysis_id=analysis_id,
            tracks=len(result.tracks),
            near_misses=len(result.near_misses),
            risk=risk["risk_score"],
            origin=origin.value,
        )

    async def _write_events(
        self,
        result: Any,
        job: dict[str, Any],
        analysis_id: str,
        origin: DataOrigin,
        assessment: Any,
    ) -> None:
        events = EventService(self._store)
        camera_id = job.get("camera_id")
        camera = job.get("camera_snapshot") or {}
        location = camera.get("location")
        base_time: datetime = job.get("created_at") or utc_now()

        payloads: list[EventCreate] = []

        for finding in result.findings:
            payloads.append(
                EventCreate(
                    event_type=finding.event_type,
                    timestamp=base_time,
                    camera_id=camera_id,
                    road_segment_id=camera.get("road_segment_id"),
                    location=location,
                    severity=finding.severity,
                    confidence=finding.confidence,
                    origin=origin,
                    model_version=result.detector_version,
                    track_ids=[finding.track_id],
                    details={**finding.details, "video_timestamp_s": round(finding.timestamp_s, 2)},
                    video_analysis_id=analysis_id,
                    frame_index=finding.frame_index,
                )
            )

        for near_miss in result.near_misses:
            payloads.append(
                EventCreate(
                    event_type=EventType.NEAR_MISS,
                    timestamp=base_time,
                    camera_id=camera_id,
                    road_segment_id=camera.get("road_segment_id"),
                    location=location,
                    severity=near_miss.severity,
                    confidence=None,  # a geometric conflict, not a classifier output
                    risk_score=near_miss.interaction_score,
                    origin=origin,
                    model_version=result.detector_version,
                    track_ids=list(near_miss.track_ids),
                    details={
                        "estimated_ttc_seconds": near_miss.estimated_ttc_s,
                        "ttc_band": near_miss.ttc_band.value if near_miss.ttc_band else None,
                        "gap_metres": near_miss.gap_m,
                        "gap_pixels": near_miss.gap_px,
                        "closing_speed_px_s": near_miss.closing_speed_px_s,
                        "risk_factors": list(near_miss.risk_factors),
                        "video_timestamp_s": round(near_miss.timestamp_s, 2),
                        "measurement": "ESTIMATED",
                    },
                    video_analysis_id=analysis_id,
                    frame_index=near_miss.frame_index,
                )
            )

        # One collision-risk event carrying the segment assessment, so the risk
        # map and analytics have a scored record to aggregate.
        if result.tracks:
            payloads.append(
                EventCreate(
                    event_type=EventType.COLLISION_RISK,
                    timestamp=base_time,
                    camera_id=camera_id,
                    road_segment_id=camera.get("road_segment_id"),
                    location=location,
                    severity=Severity.MAJOR if assessment.score >= 51 else Severity.INFO,
                    confidence=assessment.confidence,
                    risk_score=assessment.score,
                    origin=origin,
                    model_version=result.detector_version,
                    details={
                        "risk_level": assessment.level.value,
                        "factors": assessment.explain(),
                        "measurement": "ESTIMATED",
                    },
                    video_analysis_id=analysis_id,
                )
            )

        if payloads:
            written = await events.create_many(payloads)
            log.info("analysis.events_written", count=written, analysis_id=analysis_id)


def _track_summaries(result: Any) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for track in result.tracks:
        samples = result.motion.get(track.track_id, [])
        speeds = [s.speed_kmh for s in samples if s.speed_kmh is not None]
        headings = [s.heading_deg for s in samples if s.heading_deg is not None]

        path = [[round(p.x, 1), round(p.y, 1)] for p in track.path()]
        if len(path) > MAX_PATH_POINTS:
            step = len(path) / MAX_PATH_POINTS
            path = [path[int(index * step)] for index in range(MAX_PATH_POINTS)]

        summaries.append(
            {
                "track_id": track.track_id,
                "vehicle_class": track.vehicle_class.value,
                "first_frame": track.first_seen_frame,
                "last_frame": track.last_seen_frame,
                "duration_s": round(track.duration_s, 2),
                "point_count": len(track.points),
                "mean_speed_kmh": round(sum(speeds) / len(speeds), 1) if speeds else None,
                "heading_deg": round(sum(headings) / len(headings), 1) if headings else None,
                "path": path,
            }
        )
    return summaries


def _timeline(result: Any) -> list[dict[str, Any]]:
    from app.services.event_service import EVENTS  # noqa: F401 - keeps import graph explicit

    entries: list[dict[str, Any]] = []

    for finding in result.findings:
        entries.append(
            {
                "timestamp_s": round(finding.timestamp_s, 2),
                "frame_index": finding.frame_index,
                "event_type": finding.event_type.value,
                "severity": finding.severity.value,
                "track_ids": [finding.track_id],
                "confidence": round(finding.confidence, 2),
                "risk_score": None,
                "label": finding.event_type.value.replace("_", " ").title(),
            }
        )

    for near_miss in result.near_misses:
        entries.append(
            {
                "timestamp_s": round(near_miss.timestamp_s, 2),
                "frame_index": near_miss.frame_index,
                "event_type": EventType.NEAR_MISS.value,
                "severity": near_miss.severity.value,
                "track_ids": list(near_miss.track_ids),
                "confidence": None,
                "risk_score": near_miss.interaction_score,
                "label": (
                    f"Near miss · est. TTC {near_miss.estimated_ttc_s:.1f}s"
                    if near_miss.estimated_ttc_s is not None
                    else "Near miss"
                ),
            }
        )

    entries.sort(key=lambda entry: entry["timestamp_s"])
    return entries
