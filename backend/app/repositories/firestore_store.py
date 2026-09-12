"""Firestore implementation of :class:`DocumentStore`.

The Firebase Admin SDK is synchronous and blocking, so every call is dispatched
to a worker thread. Using the async Firestore client instead would tie the
backend to a different credential path than Auth and Storage, which is not a
trade worth making for a service whose slowest operation is video analysis.

Firestore specifics handled here so no caller has to know them:

* ``DatetimeWithNanoseconds`` is converted to plain timezone-aware
  ``datetime`` on read.
* Cursors are the document id, resolved to a snapshot for ``start_after``.
  Firestore requires a snapshot or field values, not an offset.
* ``update`` is pre-checked for existence, because Firestore's ``set(merge=True)``
  would create a document and its ``update`` raises a provider-specific error.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import structlog

from app.core.errors import ConflictError, DependencyUnavailableError, NotFoundError
from app.repositories.base import DocumentStore, Filter, Operator, Page, Query

if TYPE_CHECKING:  # pragma: no cover - typing only
    from google.cloud.firestore_v1 import Client as FirestoreClient

log = structlog.get_logger(__name__)

#: Largest number of writes Firestore accepts in one batch.
_BATCH_LIMIT = 500


class FirestoreDocumentStore(DocumentStore):
    """Firestore-backed document store."""

    def __init__(self, client: FirestoreClient, project_id: str | None = None) -> None:
        self._client = client
        self._project_id = project_id

    # ------------------------------------------------------------------ reads

    async def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        def _get() -> dict[str, Any] | None:
            snapshot = self._client.collection(collection).document(document_id).get()
            if not snapshot.exists:
                return None
            return _from_snapshot(snapshot)

        return await asyncio.to_thread(_get)

    async def query(self, collection: str, query: Query | None = None) -> Page:
        request = query or Query()

        def _query() -> Page:
            reference: Any = self._client.collection(collection)

            for predicate in request.filters:
                reference = reference.where(
                    field_path=predicate.field,
                    op_string=_operator_string(predicate),
                    value=predicate.value,
                )
            for order in request.orders:
                reference = reference.order_by(
                    order.field, direction="DESCENDING" if order.descending else "ASCENDING"
                )

            if request.cursor:
                anchor = self._client.collection(collection).document(request.cursor).get()
                # A deleted cursor document restarts the listing rather than
                # skipping the remainder of the collection.
                if anchor.exists:
                    reference = reference.start_after(anchor)

            if request.limit is not None:
                # Fetch one extra to learn whether another page exists without
                # a second round trip.
                reference = reference.limit(request.limit + 1)

            snapshots = list(reference.stream())

            if request.limit is not None and len(snapshots) > request.limit:
                page = snapshots[: request.limit]
                return Page(
                    documents=[_from_snapshot(item) for item in page],
                    next_cursor=page[-1].id,
                )
            return Page(documents=[_from_snapshot(item) for item in snapshots], next_cursor=None)

        return await self._guarded(_query)

    async def count(self, collection: str, query: Query | None = None) -> int:
        request = query or Query()

        def _count() -> int:
            reference: Any = self._client.collection(collection)
            for predicate in request.filters:
                reference = reference.where(
                    field_path=predicate.field,
                    op_string=_operator_string(predicate),
                    value=predicate.value,
                )
            # Server-side aggregation: billed per index read, not per document.
            result = reference.count().get()
            return int(result[0][0].value)

        return await self._guarded(_count)

    # ----------------------------------------------------------------- writes

    async def create(
        self, collection: str, data: dict[str, Any], document_id: str | None = None
    ) -> dict[str, Any]:
        def _create() -> dict[str, Any]:
            reference = (
                self._client.collection(collection).document(document_id)
                if document_id
                else self._client.collection(collection).document()
            )
            if document_id and reference.get().exists:
                raise ConflictError(
                    f"Document {document_id} already exists in {collection}.",
                    details={"collection": collection, "id": document_id},
                )
            payload = {key: value for key, value in data.items() if key != "id"}
            reference.set(payload)
            return {**_normalise(payload), "id": reference.id}

        return await self._guarded(_create)

    async def update(self, collection: str, document_id: str, data: dict[str, Any]) -> dict[str, Any]:
        def _update() -> dict[str, Any]:
            reference = self._client.collection(collection).document(document_id)
            snapshot = reference.get()
            if not snapshot.exists:
                raise NotFoundError(
                    f"Document {document_id} not found in {collection}.",
                    details={"collection": collection, "id": document_id},
                )
            payload = {key: value for key, value in data.items() if key != "id"}
            reference.update(payload)
            return {**_from_snapshot(snapshot), **_normalise(payload), "id": document_id}

        return await self._guarded(_update)

    async def delete(self, collection: str, document_id: str) -> None:
        def _delete() -> None:
            # Firestore deletes are idempotent, matching the interface contract.
            self._client.collection(collection).document(document_id).delete()

        await self._guarded(_delete)

    async def bulk_create(self, collection: str, documents: Iterable[dict[str, Any]]) -> int:
        entries = list(documents)
        if not entries:
            return 0

        def _bulk() -> int:
            written = 0
            reference = self._client.collection(collection)
            for start in range(0, len(entries), _BATCH_LIMIT):
                batch = self._client.batch()
                for entry in entries[start : start + _BATCH_LIMIT]:
                    document_id = entry.get("id")
                    target = reference.document(document_id) if document_id else reference.document()
                    batch.set(target, {key: value for key, value in entry.items() if key != "id"})
                    written += 1
                batch.commit()
            return written

        return await self._guarded(_bulk)

    # ----------------------------------------------------------------- health

    async def health(self) -> dict[str, Any]:
        def _probe() -> dict[str, Any]:
            # Cheapest possible reachability check: one limited read against a
            # collection that is expected to be tiny.
            list(self._client.collection("settings").limit(1).stream())
            return {"backend": "firestore", "project_id": self._project_id, "reachable": True}

        try:
            return await asyncio.to_thread(_probe)
        except Exception as error:  # noqa: BLE001 - health must never raise
            log.warning("firestore.health_check_failed", error=str(error))
            return {
                "backend": "firestore",
                "project_id": self._project_id,
                "reachable": False,
                "error": str(error),
            }

    # ---------------------------------------------------------------- helpers

    async def _guarded(self, operation: Any) -> Any:
        """Run a blocking Firestore call, translating transport failures.

        Application errors raised inside the callable pass through unchanged;
        anything else becomes a 503, so a Firestore outage is reported as an
        unavailable dependency rather than an opaque 500.
        """
        from app.core.errors import TrajyxError

        try:
            return await asyncio.to_thread(operation)
        except TrajyxError:
            raise
        except Exception as error:  # noqa: BLE001 - deliberately broad boundary
            log.error("firestore.operation_failed", error=str(error), error_type=type(error).__name__)
            raise DependencyUnavailableError(
                "Firestore is unavailable. The request was not completed.",
                details={"cause": type(error).__name__},
            ) from error


def _operator_string(predicate: Filter) -> str:
    """Map the shared operator set onto Firestore's strings."""
    if predicate.op is Operator.NOT_IN:
        return "not-in"
    if predicate.op is Operator.ARRAY_CONTAINS:
        return "array_contains"
    return predicate.op.value


def _normalise(value: Any) -> Any:
    """Convert Firestore-native values into plain Python.

    ``DatetimeWithNanoseconds`` subclasses ``datetime`` but serialises
    differently; normalising on the way out means nothing downstream needs to
    know it exists.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, dict):
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def _from_snapshot(snapshot: Any) -> dict[str, Any]:
    data = snapshot.to_dict() or {}
    return {**_normalise(data), "id": snapshot.id}
