"""Model registry and measured performance.

The registry is derived from what has actually run. A model version appears
here because an analysis job used it, not because someone typed it into a
table — a registry that can list a model the platform has never executed is a
registry that can lie about what is deployed.

Accuracy metrics are the hard case. Precision, recall and F1 require a
labelled evaluation set, and this build has not been given one. They are
therefore reported as unavailable with that reason, in every response. They
are never filled in from detection confidence, which measures the model's own
certainty and says nothing about whether it was right.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from trajyx_shared.domain import JobStatus, ModelHealth

from app.api.deps import StoreDep, require_staff
from app.repositories.base import Query as StoreQuery
from app.repositories.base import utc_now
from app.schemas.common import ResponseModel
from app.schemas.dashboard import Metric

router = APIRouter(prefix="/models", tags=["model health"])

ANALYSES = "video_analysis"
JOBS = "video_jobs"
REGISTRY = "model_versions"

#: Above this mean latency a model is flagged for attention. Chosen as the
#: point at which a 30 fps camera can no longer be processed in real time on
#: one worker (1000 / 30 ≈ 33 ms), doubled to allow for batching headroom.
LATENCY_WARNING_MS = 66.0
LATENCY_CRITICAL_MS = 200.0

#: A model whose jobs fail more often than this needs attention regardless of
#: how fast the successful runs were.
FAILURE_WARNING_RATE = 0.05
FAILURE_CRITICAL_RATE = 0.20

ACCURACY_UNAVAILABLE = (
    "No labelled evaluation set has been run against this version, so precision, recall "
    "and F1 are unknown. Detection confidence is not a substitute: it is the model's own "
    "certainty, not a measure of whether it was correct."
)


class LatencyBlock(ResponseModel):
    """Measured inference latency, per frame."""

    mean_ms: Metric
    median_ms: Metric
    p95_ms: Metric
    slowest_ms: Metric
    samples: int = Field(description="Analysis runs the latency figures are computed from.")


class AccuracyBlock(ResponseModel):
    """Accuracy metrics — reported only if an evaluation run produced them."""

    precision: Metric
    recall: Metric
    f1: Metric
    dataset_version: str | None = None
    evaluated_at: datetime | None = None


class ModelVersionResponse(ResponseModel):
    name: str
    version: str | None = Field(
        description=(
            "The component's version, or null when the analysis record does not store one. "
            "Never borrowed from a sibling component: a tracker labelled with the detector's "
            "version would attribute its runs to a build that never produced them."
        )
    )
    role: str = Field(description="What the component does: detection, tracking, risk.")
    health: ModelHealth
    health_reason: str = Field(description="Why it has that health state, in plain words.")

    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    runs: int = Field(description="Analysis runs recorded against this version.")
    frames_processed: int
    detections: int

    latency: LatencyBlock
    accuracy: AccuracyBlock

    jobs_succeeded: int
    jobs_failed: int
    failure_rate: Metric

    registered: bool = Field(
        description="True when a registry record exists as well as observed runs."
    )
    notes: list[str] = Field(
        default_factory=list, description="Caveats an operator should read before trusting it."
    )


class ModelHealthResponse(ResponseModel):
    generated_at: datetime
    window_hours: int
    models: list[ModelVersionResponse]
    evaluation_available: bool = Field(
        description="False when no labelled evaluation has ever been run against any version."
    )
    evaluation_note: str


def _metric(value: float | None, unit: str, reason: str) -> Metric:
    return Metric.measured(round(value, 1), unit=unit) if value is not None else Metric.unavailable(reason, unit=unit)


def _percentile(samples: list[float], fraction: float) -> float:
    """Nearest-rank percentile.

    `statistics.quantiles` interpolates and needs at least two points; an
    operator reading "p95" of three runs wants one of those three numbers, not
    a value between them that no run produced.
    """
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


@router.get(
    "/health",
    response_model=ModelHealthResponse,
    summary="Registered models and their measured performance",
    dependencies=[Depends(require_staff)],
)
async def model_health(
    store: StoreDep,
    window_hours: Annotated[int, Query(ge=1, le=8760)] = 720,
) -> ModelHealthResponse:
    now = utc_now()
    since = now - timedelta(hours=window_hours)

    analyses = [
        document
        for document in (await store.query(ANALYSES)).documents
        if isinstance(document.get("created_at"), datetime) and document["created_at"] >= since
    ]
    jobs = [
        document
        for document in (await store.query(JOBS)).documents
        if isinstance(document.get("created_at"), datetime) and document["created_at"] >= since
    ]
    registry = {
        (str(record.get("name")), str(record.get("version"))): record
        for record in (await store.query(REGISTRY, StoreQuery())).documents
    }

    # Group observed runs by the component that produced them. Detector and
    # tracker are separate versions even though one run exercises both.
    observed: dict[tuple[str, str | None, str], list[dict[str, Any]]] = defaultdict(list)
    for analysis in analyses:
        detector = str(analysis.get("detector_name") or "unknown")
        detector_version = analysis.get("detector_version")
        observed[
            (detector, str(detector_version) if detector_version else None, "detection")
        ].append(analysis)

        tracker = analysis.get("tracker_name")
        if tracker:
            # The tracker's own version, never the detector's. The pipeline
            # does not currently record one, so this is usually None and the
            # response says so rather than implying a build it cannot name.
            tracker_version = analysis.get("tracker_version")
            observed[
                (str(tracker), str(tracker_version) if tracker_version else None, "tracking")
            ].append(analysis)

    failed_jobs = sum(1 for job in jobs if str(job.get("status")) == JobStatus.FAILED.value)
    completed_jobs = sum(1 for job in jobs if str(job.get("status")) == JobStatus.COMPLETED.value)

    models: list[ModelVersionResponse] = []
    for (name, version, role), runs in sorted(
        observed.items(), key=lambda item: (item[0][2], item[0][0], item[0][1] or "")
    ):
        # `inference_ms_per_frame` is the *detector's* time per frame. The
        # pipeline records no separate tracker timing, so attributing this
        # figure to the tracking stage would report the detector's cost as
        # the tracker's. Latency is therefore only claimed for detection.
        latencies = (
            [
                float(run["inference_ms_per_frame"])
                for run in runs
                if isinstance(run.get("inference_ms_per_frame"), int | float)
            ]
            if role == "detection"
            else []
        )
        timestamps = [run["created_at"] for run in runs if isinstance(run.get("created_at"), datetime)]

        no_latency = (
            "No run recorded an inference time for this version."
            if role == "detection"
            else (
                "The pipeline times the detector, not the tracker, so no per-frame figure "
                "exists for this stage. The detector's time is not reported here, because it "
                "is not this component's cost."
            )
        )
        latency = LatencyBlock(
            mean_ms=_metric(statistics.fmean(latencies) if latencies else None, "ms", no_latency),
            median_ms=_metric(statistics.median(latencies) if latencies else None, "ms", no_latency),
            p95_ms=_metric(_percentile(latencies, 0.95) if latencies else None, "ms", no_latency),
            slowest_ms=_metric(max(latencies) if latencies else None, "ms", no_latency),
            samples=len(latencies),
        )

        record = registry.get((name, version)) if version is not None else None
        accuracy = _accuracy_from_registry(record)

        total_jobs = completed_jobs + failed_jobs
        failure_rate = (failed_jobs / total_jobs) if total_jobs else None
        health, reason = _health(
            mean_latency=statistics.fmean(latencies) if latencies else None,
            failure_rate=failure_rate,
            runs=len(runs),
            accuracy=accuracy,
        )

        notes: list[str] = []
        if accuracy.precision.available is False:
            notes.append("Accuracy has not been evaluated; only speed and throughput are measured.")
        if record is None:
            notes.append(
                "Observed from analysis runs only — no registry record exists for this version."
            )
        if version is None:
            notes.append(
                "The analysis record stores no version for this component, so its runs cannot be "
                "attributed to a specific build."
            )

        models.append(
            ModelVersionResponse(
                name=name,
                version=version,
                role=role,
                health=health,
                health_reason=reason,
                first_seen_at=min(timestamps) if timestamps else None,
                last_seen_at=max(timestamps) if timestamps else None,
                runs=len(runs),
                frames_processed=sum(
                    int(run.get("frames_analysed", 0) or 0) for run in runs
                ),
                detections=sum(int(run.get("detection_count", 0) or 0) for run in runs),
                latency=latency,
                accuracy=accuracy,
                jobs_succeeded=completed_jobs,
                jobs_failed=failed_jobs,
                failure_rate=_metric(
                    failure_rate * 100 if failure_rate is not None else None,
                    "%",
                    "No analysis job has finished in this window.",
                ),
                registered=record is not None,
                notes=notes,
            )
        )

    evaluated = any(model.accuracy.precision.available for model in models)
    return ModelHealthResponse(
        generated_at=now,
        window_hours=window_hours,
        models=models,
        evaluation_available=evaluated,
        evaluation_note=(
            "Accuracy figures shown come from a recorded evaluation run."
            if evaluated
            else ACCURACY_UNAVAILABLE
        ),
    )


def _accuracy_from_registry(record: dict[str, Any] | None) -> AccuracyBlock:
    """Read accuracy from a registry record, if one carries a real evaluation.

    A registry record only counts when it names the dataset it was evaluated
    against. A precision figure with no dataset behind it is not a measurement
    of anything, so it is treated as absent.
    """
    if record is None or not record.get("dataset_version"):
        return AccuracyBlock(
            precision=Metric.unavailable(ACCURACY_UNAVAILABLE),
            recall=Metric.unavailable(ACCURACY_UNAVAILABLE),
            f1=Metric.unavailable(ACCURACY_UNAVAILABLE),
        )

    def read(field: str) -> Metric:
        value = record.get(field)
        if not isinstance(value, int | float):
            return Metric.unavailable(
                f"The evaluation run against {record['dataset_version']} did not record {field}."
            )
        return Metric.measured(round(float(value), 3))

    evaluated_at = record.get("evaluated_at")
    return AccuracyBlock(
        precision=read("precision"),
        recall=read("recall"),
        f1=read("f1"),
        dataset_version=str(record["dataset_version"]),
        evaluated_at=evaluated_at if isinstance(evaluated_at, datetime) else None,
    )


def _health(
    *,
    mean_latency: float | None,
    failure_rate: float | None,
    runs: int,
    accuracy: AccuracyBlock,
) -> tuple[ModelHealth, str]:
    """Derive a health state from what has been measured.

    Health is deliberately about throughput and reliability, the two things
    this platform measures. It is not a judgement about accuracy, because
    accuracy has not been measured — a model reported HEALTHY here is fast and
    does not crash, and that is all the claim means.
    """
    if runs == 0:
        return ModelHealth.UNKNOWN, "No analysis run has used this version in the window."

    if failure_rate is not None and failure_rate >= FAILURE_CRITICAL_RATE:
        return (
            ModelHealth.NEEDS_ATTENTION,
            f"{failure_rate:.0%} of analysis jobs failed in this window.",
        )
    if mean_latency is not None and mean_latency >= LATENCY_CRITICAL_MS:
        return (
            ModelHealth.NEEDS_ATTENTION,
            f"Mean inference is {mean_latency:.0f} ms per frame, far slower than real time.",
        )
    if failure_rate is not None and failure_rate >= FAILURE_WARNING_RATE:
        return ModelHealth.WARNING, f"{failure_rate:.0%} of analysis jobs failed in this window."
    if mean_latency is not None and mean_latency >= LATENCY_WARNING_MS:
        return (
            ModelHealth.WARNING,
            f"Mean inference is {mean_latency:.0f} ms per frame; a 30 fps stream needs under 33 ms.",
        )
    if mean_latency is None:
        return ModelHealth.UNKNOWN, "No run recorded an inference time, so speed is unknown."

    suffix = " Accuracy is unevaluated." if not accuracy.precision.available else ""
    return (
        ModelHealth.HEALTHY,
        f"{runs} run(s) completed at {mean_latency:.0f} ms per frame with no failures.{suffix}",
    )
