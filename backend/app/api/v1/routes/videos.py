"""Video upload, analysis jobs and results."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import Response
from trajyx_shared.domain import JobStatus

from app.api.deps import CurrentUser, SettingsDep, StorageDep, StoreDep, require_operator, require_staff
from app.core.errors import (
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaError,
    ValidationError,
)
from app.repositories.base import Filter, utc_now
from app.repositories.base import Query as StoreQuery
from app.schemas.common import Page
from app.schemas.jobs import AnalyseRequest, VideoAnalysisResponse, VideoJobResponse
from app.services.storage import video_key

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/videos", tags=["video analysis"])

JOBS = "video_jobs"
ANALYSIS = "video_analysis"
CAMERAS = "cameras"

#: Read the upload in 4 MiB chunks so a 512 MiB file never sits in memory
#: whole, and so the size limit is enforced as it streams rather than after.
CHUNK_BYTES = 4 * 1024 * 1024


@router.post(
    "/upload",
    response_model=VideoJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload footage and create a job",
    responses={
        413: {"description": "File exceeds the configured size limit."},
        415: {"description": "Unsupported video format."},
    },
)
async def upload_video(
    request: Request,
    store: StoreDep,
    storage: StorageDep,
    settings: SettingsDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
    file: Annotated[UploadFile, File(description="Video file.")],
    camera_id: Annotated[str | None, Form(description="Camera this footage came from.")] = None,
) -> VideoJobResponse:
    """Store footage and create a `QUEUED` job.

    Analysis is started separately by `POST /videos/{id}/analyze`, so an
    operator can upload several clips and then run them, and so a failed
    analysis can be retried without re-uploading.
    """
    del request

    filename = (file.filename or "upload").strip()
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""

    if suffix not in settings.allowed_video_extensions:
        raise UnsupportedMediaError(
            f"{suffix or 'This file'} is not an accepted video format.",
            details={"allowed": settings.allowed_video_extensions},
        )
    if file.content_type and file.content_type not in settings.allowed_video_content_types:
        raise UnsupportedMediaError(
            f"Content type {file.content_type} is not accepted.",
            details={"allowed": settings.allowed_video_content_types},
        )

    camera: dict | None = None
    if camera_id:
        camera = await store.get(CAMERAS, camera_id)
        if camera is None:
            raise NotFoundError(f"Camera {camera_id} not found.", details={"camera_id": camera_id})

    # Create the job first so the storage key is derived from a real id.
    job = await store.create(
        JOBS,
        {
            "status": JobStatus.QUEUED.value,
            "filename": filename,
            "size_bytes": 0,
            "content_type": file.content_type or "video/mp4",
            "camera_id": camera_id,
            # Snapshot the camera geometry: later edits must not silently
            # change what a completed analysis was based on.
            "camera_snapshot": _camera_snapshot(camera) if camera else None,
            "storage_key": "",
            "created_at": utc_now(),
            "created_by": user.user_id,
        },
    )
    job_id = str(job["id"])
    key = video_key(job_id, filename)

    written = 0
    try:
        # Streamed to storage in chunks, checking the limit as it goes.
        import io

        buffer = io.BytesIO()
        while chunk := await file.read(CHUNK_BYTES):
            written += len(chunk)
            if written > settings.max_upload_bytes:
                raise PayloadTooLargeError(
                    f"Upload exceeds the {settings.max_upload_bytes // (1024 * 1024)} MiB limit.",
                    details={"limit_bytes": settings.max_upload_bytes},
                )
            buffer.write(chunk)

        if written == 0:
            raise ValidationError("The uploaded file is empty.")

        buffer.seek(0)
        await storage.put(key, buffer, file.content_type or "video/mp4")
    except Exception:
        # Do not leave a job pointing at footage that was never stored.
        await store.delete(JOBS, job_id)
        raise

    document = await store.update(
        JOBS, job_id, {"storage_key": key, "size_bytes": written, "frame_stride": settings.frame_stride}
    )
    log.info("video.uploaded", job_id=job_id, bytes=written, camera_id=camera_id, by=user.user_id)

    return VideoJobResponse.from_document(
        document, camera_name=str(camera.get("name")) if camera else None
    )


@router.post(
    "/{job_id}/analyze",
    response_model=VideoJobResponse,
    summary="Start analysis",
    responses={404: {"description": "Job not found."}, 409: {"description": "Already running."}},
)
async def analyze_video(
    job_id: str,
    payload: AnalyseRequest,
    request: Request,
    store: StoreDep,
    _user: Annotated[CurrentUser, Depends(require_operator)],
) -> VideoJobResponse:
    """Queue the job and return immediately.

    The response is the job, not the result: analysis takes minutes, and an
    HTTP request that waited for it would time out. Poll `GET /videos/{id}`
    for progress.
    """
    job = await store.get(JOBS, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found.", details={"job_id": job_id})

    current = JobStatus(str(job.get("status", JobStatus.QUEUED.value)))
    if current is JobStatus.PROCESSING:
        from app.core.errors import ConflictError

        raise ConflictError("This job is already being analysed.")

    queue = getattr(request.app.state, "job_queue", None)
    if queue is None:  # pragma: no cover - indicates a broken lifespan
        from app.core.errors import DependencyUnavailableError

        raise DependencyUnavailableError("The analysis worker is not available.")

    document = await store.update(
        JOBS,
        job_id,
        {
            "status": JobStatus.QUEUED.value,
            "error": None,
            "frame_stride": payload.frame_stride or job.get("frame_stride"),
            "progress": {
                "stage": "queued",
                "percent": 0.0,
                "frames_processed": 0,
                "frames_total": 0,
                "detections": 0,
                "active_tracks": 0,
            },
        },
    )
    await queue.enqueue(job_id, payload)
    log.info("video.analysis_queued", job_id=job_id, simulate=payload.simulate)

    return VideoJobResponse.from_document(document)


@router.get(
    "",
    response_model=Page[VideoJobResponse],
    summary="List jobs",
    dependencies=[Depends(require_staff)],
)
async def list_jobs(
    store: StoreDep,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    camera_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[VideoJobResponse]:
    query = StoreQuery().order_by("created_at", descending=True).take(limit).after(cursor)
    if job_status is not None:
        query = query.where(Filter.eq("status", job_status.value))
    if camera_id is not None:
        query = query.where(Filter.eq("camera_id", camera_id))

    page = await store.query(JOBS, query)
    names = await _camera_names(store, page.documents)

    return Page(
        items=[
            VideoJobResponse.from_document(document, names.get(str(document.get("camera_id"))))
            for document in page.documents
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{job_id}",
    response_model=VideoJobResponse,
    summary="Job status and progress",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "Job not found."}},
)
async def read_job(job_id: str, store: StoreDep) -> VideoJobResponse:
    job = await store.get(JOBS, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found.", details={"job_id": job_id})

    camera_name: str | None = None
    if job.get("camera_id"):
        camera = await store.get(CAMERAS, str(job["camera_id"]))
        camera_name = str(camera.get("name")) if camera else None

    return VideoJobResponse.from_document(job, camera_name)


@router.get(
    "/{job_id}/analysis",
    response_model=VideoAnalysisResponse,
    summary="Analysis result",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "No completed analysis for this job."}},
)
async def read_analysis(job_id: str, store: StoreDep) -> VideoAnalysisResponse:
    """The full result: counts, tracks, timeline, risk and unavailable checks.

    `unavailable_checks` matters as much as the findings: it distinguishes
    "no violations occurred" from "this camera cannot detect that violation".
    """
    page = await store.query(ANALYSIS, StoreQuery().where(Filter.eq("job_id", job_id)).take(1))
    if not page.documents:
        raise NotFoundError(
            f"No completed analysis for job {job_id}.", details={"job_id": job_id}
        )
    return VideoAnalysisResponse.from_document(page.documents[0])


@router.get(
    "/{job_id}/media",
    summary="Stream the annotated video",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "No annotated video for this job."}},
)
async def read_media(
    job_id: str,
    store: StoreDep,
    storage: StorageDep,
    variant: Annotated[str, Query(pattern="^(source|annotated)$")] = "annotated",
) -> Response:
    """Serve the source or annotated video.

    Served through the API rather than a public URL: footage is the most
    sensitive data in the system, and a public link cannot be revoked.
    """
    job = await store.get(JOBS, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found.", details={"job_id": job_id})

    key = job.get("annotated_key") if variant == "annotated" else job.get("storage_key")
    if not key:
        raise NotFoundError(
            f"No {variant} video available for job {job_id}.",
            details={"job_id": job_id, "variant": variant},
        )

    data = await storage.get_bytes(str(key))
    return Response(
        content=data,
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{job_id}-{variant}.mp4"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete(
    "/{job_id}",
    summary="Delete a job and its footage",
    responses={404: {"description": "Job not found."}},
)
async def delete_job(
    job_id: str,
    store: StoreDep,
    storage: StorageDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
) -> dict[str, str]:
    """Remove a job, its stored footage and its annotated output.

    Derived events are retained: they are the safety history other analysis
    depends on, and deleting them would corrupt road-segment risk.
    """
    job = await store.get(JOBS, job_id)
    if job is None:
        raise NotFoundError(f"Job {job_id} not found.", details={"job_id": job_id})

    for key in (job.get("storage_key"), job.get("annotated_key")):
        if key:
            await storage.delete(str(key))

    await store.delete(JOBS, job_id)
    log.info("video.job_deleted", job_id=job_id, by=user.user_id)
    return {"message": "Job and footage deleted. Derived events were retained."}


# -------------------------------------------------------------------- helpers


def _camera_snapshot(camera: dict) -> dict:
    """The geometry an analysis was based on, frozen at upload time."""
    return {
        "name": camera.get("name"),
        "road_segment_id": camera.get("road_segment_id"),
        "location": camera.get("location"),
        "frame_width": camera.get("frame_width"),
        "frame_height": camera.get("frame_height"),
        "calibration": camera.get("calibration"),
        "stop_line": camera.get("stop_line"),
        "lane_directions": camera.get("lane_directions"),
        "signal_state": camera.get("signal_state"),
    }


async def _camera_names(store, documents) -> dict[str, str]:  # noqa: ANN001
    wanted = {str(d.get("camera_id")) for d in documents if d.get("camera_id")}
    if not wanted:
        return {}
    page = await store.query(CAMERAS)
    return {
        str(camera["id"]): str(camera.get("name", ""))
        for camera in page.documents
        if str(camera["id"]) in wanted
    }
