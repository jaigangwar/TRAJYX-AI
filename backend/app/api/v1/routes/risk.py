"""Road segments, risk zones and the driver alert endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from trajyx_shared.domain import RiskLevel

from app.api.deps import (
    CurrentUser,
    StoreDep,
    require_admin,
    require_driver,
    require_operator,
    require_staff,
)
from app.geo.service import GeoService
from app.schemas.common import Acknowledgement
from app.schemas.geo import (
    AlertEvaluationResponse,
    NearbyRiskRequest,
    RiskZoneResponse,
    RoadSegmentCreate,
    RoadSegmentResponse,
    RoadSegmentUpdate,
    SegmentDetailResponse,
)

router = APIRouter(prefix="/risk", tags=["risk intelligence"])


def _service(store: StoreDep) -> GeoService:
    return GeoService(store)


ServiceDep = Annotated[GeoService, Depends(_service)]


# --------------------------------------------------------------- road segments


@router.get(
    "/segments",
    response_model=list[RoadSegmentResponse],
    summary="List road segments, riskiest first",
    dependencies=[Depends(require_staff)],
)
async def list_segments(
    service: ServiceDep,
    minimum_risk: Annotated[float | None, Query(ge=0, le=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[RoadSegmentResponse]:
    return await service.list_segments(minimum_risk=minimum_risk, limit=limit)


@router.post(
    "/segments",
    response_model=RoadSegmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Define a road segment",
    responses={409: {"description": "A segment with that name already exists."}},
)
async def create_segment(
    payload: RoadSegmentCreate,
    service: ServiceDep,
    _user: Annotated[CurrentUser, Depends(require_operator)],
) -> RoadSegmentResponse:
    """Define a segment.

    Risk is left null until events are attributed to it: a segment with no
    observations has unknown risk, not low risk.
    """
    return await service.create_segment(payload)


@router.get(
    "/segments/{segment_id}",
    response_model=SegmentDetailResponse,
    summary="Segment detail with risk by hour",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "Segment not found."}},
)
async def read_segment(segment_id: str, service: ServiceDep) -> SegmentDetailResponse:
    """Everything the risk-map detail panel shows.

    Risk is scored per hour as well as overall, because the same junction is
    quiet at 06:00 and dangerous at 19:00 and a single number hides that.
    """
    return await service.segment_detail(segment_id)


@router.patch(
    "/segments/{segment_id}",
    response_model=RoadSegmentResponse,
    summary="Update a road segment",
    responses={404: {"description": "Segment not found."}},
)
async def update_segment(
    segment_id: str,
    payload: RoadSegmentUpdate,
    service: ServiceDep,
    _user: Annotated[CurrentUser, Depends(require_operator)],
) -> RoadSegmentResponse:
    return await service.update_segment(segment_id, payload)


@router.delete(
    "/segments/{segment_id}",
    response_model=Acknowledgement,
    summary="Delete a road segment",
    responses={404: {"description": "Segment not found."}},
)
async def delete_segment(
    segment_id: str,
    service: ServiceDep,
    _user: Annotated[CurrentUser, Depends(require_admin)],
) -> Acknowledgement:
    await service.delete_segment(segment_id)
    return Acknowledgement(message="Segment and its derived risk zones removed.")


# ------------------------------------------------------------------ risk zones


@router.get(
    "/zones",
    response_model=list[RiskZoneResponse],
    summary="List risk zones, highest first",
)
async def list_zones(
    service: ServiceDep,
    _user: CurrentUser,
    minimum_level: Annotated[RiskLevel | None, Query()] = None,
) -> list[RiskZoneResponse]:
    """Risk zones.

    Readable by any signed-in user including drivers: this is aggregate road
    risk, not footage-derived detail about individual road users, and the
    mobile alert engine needs it.
    """
    return await service.list_zones(minimum_level=minimum_level)


@router.post(
    "/aggregate",
    summary="Recompute segment risk and risk zones",
    responses={403: {"description": "Operators and administrators only."}},
)
async def aggregate(
    service: ServiceDep,
    _user: Annotated[CurrentUser, Depends(require_operator)],
    window_hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24 * 7,
) -> dict[str, int]:
    """Attribute events to segments, score them, and rebuild risk zones.

    Existing zones are cleared first, so a segment that has gone quiet stops
    warning drivers about a hazard that is no longer observed.
    """
    return await service.aggregate(window_hours=window_hours)


# --------------------------------------------------------------- driver alerts


@router.post(
    "/nearby",
    response_model=AlertEvaluationResponse,
    summary="Evaluate risk around a driver and decide whether to warn",
)
async def evaluate_nearby(
    payload: NearbyRiskRequest,
    service: ServiceDep,
    user: Annotated[CurrentUser, Depends(require_driver)],
    record: Annotated[
        bool, Query(description="Record a raised alert, which starts its cooldown.")
    ] = True,
) -> AlertEvaluationResponse:
    """The driver-facing endpoint.

    Returns every nearby zone with the geometry the decision used, plus at
    most one alert. When no alert is raised but a zone was nearby,
    `suppressed_reason` says why — behind the driver, below threshold, or
    within cooldown — so the behaviour is inspectable rather than mysterious.
    """
    result = await service.evaluate_alert(payload, user_id=user.user_id)

    if result.alert is not None and record:
        await service.record_alert(result.alert, user.user_id)

    return result
