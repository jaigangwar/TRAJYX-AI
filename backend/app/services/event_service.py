"""Event storage, querying and dashboard aggregation.

Events from every source share one collection and one shape, so the violations
page, the near-miss page, the incident queue, the map layers and the exports
are all views over the same query path rather than parallel implementations.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

import structlog
from trajyx_shared.domain import (
    EVENT_CATEGORY,
    DataOrigin,
    EventCategory,
    EventType,
    ReportStatus,
    RiskLevel,
    risk_level_from_score,
)

from app.core.errors import NotFoundError
from app.repositories.base import DocumentStore, Filter, Operator, Query, utc_now
from app.schemas.events import EventCreate, EventResponse

log = structlog.get_logger(__name__)

EVENTS = "risk_events"
CAMERAS = "cameras"

#: Event types an operator reviews. Others are informational and carry no
#: review state, so a review filter must not silently exclude them.
REVIEWABLE = frozenset(
    {
        EventType.HELMET_VIOLATION,
        EventType.SEATBELT_VIOLATION,
        EventType.TRIPLE_RIDING,
        EventType.WRONG_WAY,
        EventType.RED_LIGHT_VIOLATION,
        EventType.STOP_LINE_VIOLATION,
        EventType.DANGEROUS_LANE_CHANGE,
        EventType.OVERSPEED,
        EventType.HAZARD_REPORT,
    }
)


class EventService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    # ------------------------------------------------------------------ writes

    async def create(self, payload: EventCreate) -> EventResponse:
        document = await self._store.create(
            EVENTS,
            {
                **payload.model_dump(mode="python", exclude_none=False),
                "event_type": payload.event_type.value,
                "severity": payload.severity.value,
                "origin": payload.origin.value,
                "category": EVENT_CATEGORY[payload.event_type].value,
                "review_status": (
                    ReportStatus.PENDING.value if payload.event_type in REVIEWABLE else None
                ),
                "created_at": utc_now(),
            },
        )
        return EventResponse.from_document(document)

    async def create_many(self, payloads: Iterable[EventCreate]) -> int:
        """Bulk-insert events.

        The analysis pipeline emits these in the hundreds per video; one round
        trip each would dominate the job runtime.
        """
        documents = [
            {
                **payload.model_dump(mode="python", exclude_none=False),
                "event_type": payload.event_type.value,
                "severity": payload.severity.value,
                "origin": payload.origin.value,
                "category": EVENT_CATEGORY[payload.event_type].value,
                "review_status": (
                    ReportStatus.PENDING.value if payload.event_type in REVIEWABLE else None
                ),
                "created_at": utc_now(),
            }
            for payload in payloads
        ]
        if not documents:
            return 0
        return await self._store.bulk_create(EVENTS, documents)

    async def set_review_status(
        self, event_id: str, status: ReportStatus, reviewed_by: str, note: str | None = None
    ) -> EventResponse:
        existing = await self._store.get(EVENTS, event_id)
        if existing is None:
            raise NotFoundError(f"Event {event_id} not found.", details={"event_id": event_id})

        document = await self._store.update(
            EVENTS,
            event_id,
            {
                "review_status": status.value,
                "reviewed_by": reviewed_by,
                "reviewed_at": utc_now(),
                "review_note": note,
            },
        )
        log.info("event.reviewed", event_id=event_id, status=status.value, by=reviewed_by)
        return EventResponse.from_document(document)

    # ------------------------------------------------------------------- reads

    async def get(self, event_id: str) -> EventResponse:
        document = await self._store.get(EVENTS, event_id)
        if document is None:
            raise NotFoundError(f"Event {event_id} not found.", details={"event_id": event_id})
        names = await self._camera_names({document})
        return EventResponse.from_document(document, names.get(str(document.get("camera_id"))))

    async def list_events(
        self,
        *,
        event_types: list[EventType] | None = None,
        category: EventCategory | None = None,
        camera_id: str | None = None,
        road_segment_id: str | None = None,
        review_status: ReportStatus | None = None,
        min_confidence: float | None = None,
        min_risk_score: float | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        origin: DataOrigin | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[EventResponse], str | None]:
        query = Query().order_by("timestamp", descending=True).take(limit).after(cursor)

        if event_types:
            # A single type uses equality so the composite index applies; `in`
            # would need a different index and is capped at 30 values.
            query = (
                query.where(Filter.eq("event_type", event_types[0].value))
                if len(event_types) == 1
                else query.where(Filter.in_("event_type", [item.value for item in event_types]))
            )
        if category is not None:
            query = query.where(Filter.eq("category", category.value))
        if camera_id is not None:
            query = query.where(Filter.eq("camera_id", camera_id))
        if road_segment_id is not None:
            query = query.where(Filter.eq("road_segment_id", road_segment_id))
        if review_status is not None:
            query = query.where(Filter.eq("review_status", review_status.value))
        if origin is not None:
            query = query.where(Filter.eq("origin", origin.value))
        if min_confidence is not None:
            query = query.where(Filter.gte("confidence", min_confidence))
        if min_risk_score is not None:
            query = query.where(Filter.gte("risk_score", min_risk_score))
        if since is not None:
            query = query.where(Filter.gte("timestamp", since))
        if until is not None:
            query = query.where(Filter("timestamp", Operator.LT, until))

        page = await self._store.query(EVENTS, query)
        names = await self._camera_names(page.documents)

        return (
            [
                EventResponse.from_document(document, names.get(str(document.get("camera_id"))))
                for document in page.documents
            ],
            page.next_cursor,
        )

    async def count(self, *, since: datetime | None = None, **filters: object) -> int:
        query = Query()
        if since is not None:
            query = query.where(Filter.gte("timestamp", since))
        for field, value in filters.items():
            if value is not None:
                query = query.where(Filter.eq(field, value))
        return await self._store.count(EVENTS, query)

    async def _camera_names(self, documents: Iterable[dict[str, object]]) -> dict[str, str]:
        """Resolve camera ids to names for display.

        One read of the camera registry rather than a lookup per event: the
        registry is small, and N+1 reads per table page is the classic way to
        make a dashboard slow.
        """
        wanted = {str(document.get("camera_id")) for document in documents if document.get("camera_id")}
        if not wanted:
            return {}

        page = await self._store.query(CAMERAS)
        return {
            str(camera["id"]): str(camera.get("name", ""))
            for camera in page.documents
            if str(camera["id"]) in wanted
        }

    # ------------------------------------------------------------- aggregation

    async def dashboard_counts(self, since: datetime) -> dict[str, int]:
        """Event counts for the overview KPIs, from one read.

        Counting each category separately would be one query per KPI. The
        window is bounded by `since`, so this stays proportional to recent
        activity rather than to the whole collection.
        """
        page = await self._store.query(
            EVENTS, Query().where(Filter.gte("timestamp", since)).order_by("timestamp", descending=True)
        )

        by_category: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        critical = 0
        demo = 0

        for document in page.documents:
            by_category[str(document.get("category", ""))] += 1
            by_type[str(document.get("event_type", ""))] += 1

            score = document.get("risk_score")
            if isinstance(score, int | float) and risk_level_from_score(float(score)) is RiskLevel.CRITICAL:
                critical += 1
            if str(document.get("origin")) == DataOrigin.DEMO.value:
                demo += 1

        return {
            "total": len(page.documents),
            "violations": by_category[EventCategory.VIOLATION.value],
            "behaviour": by_category[EventCategory.BEHAVIOR.value],
            "interactions": by_category[EventCategory.INTERACTION.value],
            "reports": by_category[EventCategory.REPORT.value],
            "near_misses": by_type[EventType.NEAR_MISS.value],
            "critical": critical,
            "demo": demo,
        }

    async def recent(self, limit: int = 10) -> list[EventResponse]:
        events, _ = await self.list_events(limit=limit)
        return events


def window_start(days: int = 1, now: datetime | None = None) -> datetime:
    """Start of a rolling window ending now."""
    return (now or utc_now()) - timedelta(days=days)
