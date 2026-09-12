"""Camera registry endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from trajyx_shared.domain import CameraStatus

from app.api.deps import CurrentUser, StoreDep, require_operator, require_staff
from app.schemas.cameras import CameraCreate, CameraResponse, CameraUpdate
from app.schemas.common import Acknowledgement, Page
from app.services.camera_service import CameraService

router = APIRouter(prefix="/cameras", tags=["cameras"])


def _service(store: StoreDep) -> CameraService:
    return CameraService(store)


ServiceDep = Annotated[CameraService, Depends(_service)]


@router.get(
    "",
    response_model=Page[CameraResponse],
    summary="List cameras",
    dependencies=[Depends(require_staff)],
)
async def list_cameras(
    service: ServiceDep,
    camera_status: Annotated[CameraStatus | None, Query(alias="status")] = None,
    road_segment_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[CameraResponse]:
    items, next_cursor = await service.list_cameras(
        status=camera_status, road_segment_id=road_segment_id, limit=limit, cursor=cursor
    )
    return Page(items=items, next_cursor=next_cursor)


@router.post(
    "",
    response_model=CameraResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a camera",
    responses={409: {"description": "A camera with that name already exists."}},
)
async def create_camera(
    payload: CameraCreate,
    service: ServiceDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
) -> CameraResponse:
    """Register a camera.

    It starts `OFFLINE`: nothing has reached it yet, and reporting `ONLINE`
    before a frame has arrived would put a fabricated status on the monitoring
    grid.
    """
    return await service.create(payload, created_by=user.user_id)


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    summary="Read a camera",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "Camera not found."}},
)
async def read_camera(camera_id: str, service: ServiceDep) -> CameraResponse:
    return await service.get(camera_id)


@router.patch(
    "/{camera_id}",
    response_model=CameraResponse,
    summary="Update a camera",
    responses={404: {"description": "Camera not found."}},
)
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    service: ServiceDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
) -> CameraResponse:
    """Update a camera.

    Geometry edits change what the analysis is permitted to conclude — a stop
    line enables red-light detection, calibration enables speed estimation — so
    the response reports the resulting `capabilities`.
    """
    return await service.update(camera_id, payload, updated_by=user.user_id)


@router.delete(
    "/{camera_id}",
    response_model=Acknowledgement,
    summary="Remove a camera",
    responses={404: {"description": "Camera not found."}},
)
async def delete_camera(
    camera_id: str,
    service: ServiceDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
) -> Acknowledgement:
    """Remove a camera.

    Its events are retained and keep the camera id as an opaque reference:
    deleting them would destroy safety history that other analysis depends on.
    """
    await service.delete(camera_id, deleted_by=user.user_id)
    return Acknowledgement(message="Camera removed. Its recorded events were retained.")
