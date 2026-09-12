"""Camera registry operations."""

from __future__ import annotations

import structlog
from trajyx_shared.domain import CameraStatus

from app.core.errors import ConflictError, NotFoundError
from app.repositories.base import DocumentStore, Filter, Query, utc_now
from app.schemas.cameras import CameraCreate, CameraResponse, CameraUpdate

log = structlog.get_logger(__name__)

CAMERAS = "cameras"


class CameraService:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def get(self, camera_id: str) -> CameraResponse:
        document = await self._store.get(CAMERAS, camera_id)
        if document is None:
            raise NotFoundError(f"Camera {camera_id} not found.", details={"camera_id": camera_id})
        return CameraResponse.from_document(document)

    async def list_cameras(
        self,
        status: CameraStatus | None = None,
        road_segment_id: str | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[CameraResponse], str | None]:
        query = Query().order_by("name").take(limit).after(cursor)
        if status is not None:
            query = query.where(Filter.eq("status", status.value))
        if road_segment_id is not None:
            query = query.where(Filter.eq("road_segment_id", road_segment_id))

        page = await self._store.query(CAMERAS, query)
        return [CameraResponse.from_document(document) for document in page.documents], page.next_cursor

    async def count_by_status(self) -> dict[CameraStatus, int]:
        """Camera counts per status, for the overview KPIs.

        One read and a group in memory rather than four counting queries: the
        camera registry is tens of records, not millions, and four round trips
        to Firestore would cost more than the whole collection.
        """
        page = await self._store.query(CAMERAS)
        counts = dict.fromkeys(CameraStatus, 0)
        for document in page.documents:
            try:
                status = CameraStatus(str(document.get("status", CameraStatus.OFFLINE.value)))
            except ValueError:
                status = CameraStatus.OFFLINE
            counts[status] += 1
        return counts

    async def create(self, payload: CameraCreate, created_by: str) -> CameraResponse:
        existing = await self._store.query(
            CAMERAS, Query().where(Filter.eq("name", payload.name)).take(1)
        )
        if existing.documents:
            raise ConflictError(
                f"A camera named {payload.name!r} already exists.",
                details={"name": payload.name},
            )

        document = await self._store.create(
            CAMERAS,
            {
                **payload.model_dump(mode="json", exclude_none=False),
                # A newly registered camera has not been reached yet. Claiming
                # ONLINE before a frame has arrived would be a fabricated
                # status on the Live Monitoring grid.
                "status": CameraStatus.OFFLINE.value,
                "current_risk_score": None,
                "last_event_at": None,
                "last_seen_at": None,
                "created_at": utc_now(),
                "created_by": created_by,
                "updated_at": utc_now(),
            },
        )
        log.info("camera.created", camera_id=document["id"], name=payload.name, by=created_by)
        return CameraResponse.from_document(document)

    async def update(self, camera_id: str, payload: CameraUpdate, updated_by: str) -> CameraResponse:
        # Confirm it exists first, so a typo in an id is a 404 rather than a
        # silent no-op.
        await self.get(camera_id)

        changes = payload.model_dump(mode="json", exclude_unset=True)
        if not changes:
            return await self.get(camera_id)

        if "name" in changes:
            clash = await self._store.query(
                CAMERAS, Query().where(Filter.eq("name", changes["name"])).take(2)
            )
            if any(str(document["id"]) != camera_id for document in clash.documents):
                raise ConflictError(f"A camera named {changes['name']!r} already exists.")

        document = await self._store.update(
            CAMERAS, camera_id, {**changes, "updated_at": utc_now()}
        )
        log.info("camera.updated", camera_id=camera_id, fields=sorted(changes), by=updated_by)
        return CameraResponse.from_document(document)

    async def delete(self, camera_id: str, deleted_by: str) -> None:
        await self.get(camera_id)
        await self._store.delete(CAMERAS, camera_id)
        # Events keep their camera_id as an opaque reference: deleting them
        # would destroy the safety history other analysis depends on.
        log.info("camera.deleted", camera_id=camera_id, by=deleted_by)
