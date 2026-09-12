"""Event endpoints.

One query path serves violations, near misses, behaviour events and driver
reports. The dashboard pages differ only in which filters they apply.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from trajyx_shared.domain import DataOrigin, EventCategory, EventType, ReportStatus

from app.api.deps import CurrentUser, StoreDep, require_operator, require_staff
from app.schemas.common import Page
from app.schemas.events import EventResponse
from app.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])


def _service(store: StoreDep) -> EventService:
    return EventService(store)


ServiceDep = Annotated[EventService, Depends(_service)]


@router.get(
    "",
    response_model=Page[EventResponse],
    summary="List events",
    dependencies=[Depends(require_staff)],
)
async def list_events(
    service: ServiceDep,
    event_type: Annotated[
        list[EventType] | None, Query(description="Repeat to include several types.")
    ] = None,
    category: Annotated[EventCategory | None, Query()] = None,
    camera_id: Annotated[str | None, Query()] = None,
    road_segment_id: Annotated[str | None, Query()] = None,
    review_status: Annotated[ReportStatus | None, Query()] = None,
    origin: Annotated[
        DataOrigin | None, Query(description="Filter to MEASURED to exclude demo records.")
    ] = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    min_risk_score: Annotated[float | None, Query(ge=0.0, le=100.0)] = None,
    since: Annotated[datetime | None, Query(description="Inclusive lower bound.")] = None,
    until: Annotated[datetime | None, Query(description="Exclusive upper bound.")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> Page[EventResponse]:
    """Events, newest first.

    `origin` is the honesty filter: pass `MEASURED` to exclude demo records
    entirely. Without it, demo records are included and each is labeled.
    """
    items, next_cursor = await service.list_events(
        event_types=event_type,
        category=category,
        camera_id=camera_id,
        road_segment_id=road_segment_id,
        review_status=review_status,
        origin=origin,
        min_confidence=min_confidence,
        min_risk_score=min_risk_score,
        since=since,
        until=until,
        limit=limit,
        cursor=cursor,
    )
    return Page(items=items, next_cursor=next_cursor)


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Read an event",
    dependencies=[Depends(require_staff)],
    responses={404: {"description": "Event not found."}},
)
async def read_event(event_id: str, service: ServiceDep) -> EventResponse:
    return await service.get(event_id)


@router.patch(
    "/{event_id}/review",
    response_model=EventResponse,
    summary="Set an event's review status",
    responses={404: {"description": "Event not found."}},
)
async def review_event(
    event_id: str,
    service: ServiceDep,
    user: Annotated[CurrentUser, Depends(require_operator)],
    review_status: Annotated[ReportStatus, Query(alias="status")],
    note: Annotated[str | None, Query(max_length=500)] = None,
) -> EventResponse:
    """Confirm or reject a detection.

    These decisions are the ground-truth signal the risk model learns from in
    phase 9, so the reviewer and the time are recorded alongside the outcome.
    """
    return await service.set_review_status(
        event_id, review_status, reviewed_by=user.user_id, note=note
    )
