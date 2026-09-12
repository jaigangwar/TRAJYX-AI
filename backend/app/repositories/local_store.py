"""On-disk JSON document store.

The development and demo adapter. It exists so a clean checkout runs the whole
product end to end with no cloud account, and so tests exercise the real
repository code path rather than a mock.

Design notes and honest limits:

* One JSON file per collection under ``TRAJYX_LOCAL_DATA_DIR``. Readable and
  diffable, which is genuinely useful when debugging what the pipeline wrote.
* Writes are serialised per collection by an ``asyncio.Lock`` and land through
  a temporary file plus ``os.replace``, so a crash mid-write cannot truncate a
  collection.
* File I/O runs in a worker thread, so a large collection does not block the
  event loop.
* It is **not** suitable for production: no multi-process safety, no indexes,
  and queries scan the collection. ``/health`` reports it as a degraded mode
  and startup refuses it when ``TRAJYX_ENVIRONMENT=production``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import structlog

from app.core.errors import ConflictError, NotFoundError
from app.repositories.base import DocumentStore, Filter, Operator, Order, Page, Query

log = structlog.get_logger(__name__)

_SENTINEL = object()


class LocalDocumentStore(DocumentStore):
    """JSON-file-backed implementation of :class:`DocumentStore`."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------ files

    def _path(self, collection: str) -> Path:
        # Collection names come from the contract, never from user input, but
        # rejecting separators keeps a future caller from escaping the root.
        if "/" in collection or "\\" in collection or collection in {"", ".", ".."}:
            raise ValueError(f"Invalid collection name: {collection!r}")
        return self._root / f"{collection}.json"

    def _read_sync(self, collection: str) -> dict[str, dict[str, Any]]:
        path = self._path(collection)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Surface corruption rather than silently returning an empty
            # collection, which would look like legitimate data loss.
            log.error("local_store.corrupt_collection", collection=collection, path=str(path))
            raise
        return raw if isinstance(raw, dict) else {}

    def _write_sync(self, collection: str, documents: dict[str, dict[str, Any]]) -> None:
        path = self._path(collection)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        temporary.write_text(
            json.dumps(documents, indent=2, sort_keys=True, default=_encode_json),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    async def _read(self, collection: str) -> dict[str, dict[str, Any]]:
        return await asyncio.to_thread(self._read_sync, collection)

    async def _write(self, collection: str, documents: dict[str, dict[str, Any]]) -> None:
        await asyncio.to_thread(self._write_sync, collection, documents)

    # ------------------------------------------------------------------ reads

    async def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        documents = await self._read(collection)
        found = documents.get(document_id)
        return _decode_document(found) if found is not None else None

    async def query(self, collection: str, query: Query | None = None) -> Page:
        query = query or Query()
        documents = [_decode_document(entry) for entry in (await self._read(collection)).values()]

        matched = [document for document in documents if _matches(document, query.filters)]
        _sort(matched, query.orders)

        start = _cursor_index(matched, query.cursor)
        window = matched[start:]

        if query.limit is not None and len(window) > query.limit:
            page = window[: query.limit]
            last = page[-1]
            return Page(documents=page, next_cursor=_encode_cursor(str(last.get("id", ""))))
        return Page(documents=window, next_cursor=None)

    async def count(self, collection: str, query: Query | None = None) -> int:
        query = query or Query()
        documents = (await self._read(collection)).values()
        return sum(1 for entry in documents if _matches(_decode_document(entry), query.filters))

    # ----------------------------------------------------------------- writes

    async def create(
        self, collection: str, data: dict[str, Any], document_id: str | None = None
    ) -> dict[str, Any]:
        async with self._locks[collection]:
            documents = await self._read(collection)
            new_id = document_id or uuid.uuid4().hex

            if new_id in documents:
                raise ConflictError(
                    f"Document {new_id} already exists in {collection}.",
                    details={"collection": collection, "id": new_id},
                )

            record = {**data, "id": new_id}
            documents[new_id] = record
            await self._write(collection, documents)
            return _decode_document(record)

    async def update(self, collection: str, document_id: str, data: dict[str, Any]) -> dict[str, Any]:
        async with self._locks[collection]:
            documents = await self._read(collection)
            existing = documents.get(document_id)
            if existing is None:
                raise NotFoundError(
                    f"Document {document_id} not found in {collection}.",
                    details={"collection": collection, "id": document_id},
                )

            # `id` is identity, not data: a payload must never rewrite it.
            merged = {**existing, **data, "id": document_id}
            documents[document_id] = merged
            await self._write(collection, documents)
            return _decode_document(merged)

    async def delete(self, collection: str, document_id: str) -> None:
        async with self._locks[collection]:
            documents = await self._read(collection)
            if documents.pop(document_id, None) is not None:
                await self._write(collection, documents)

    async def bulk_create(self, collection: str, documents: Iterable[dict[str, Any]]) -> int:
        incoming = list(documents)
        if not incoming:
            return 0

        async with self._locks[collection]:
            existing = await self._read(collection)
            for entry in incoming:
                new_id = str(entry.get("id") or uuid.uuid4().hex)
                existing[new_id] = {**entry, "id": new_id}
            await self._write(collection, existing)
            return len(incoming)

    # ----------------------------------------------------------------- health

    async def health(self) -> dict[str, Any]:
        collections = sorted(path.stem for path in self._root.glob("*.json"))
        writable = os.access(self._root, os.W_OK)
        return {
            "backend": "local",
            "root": str(self._root),
            "writable": writable,
            "collections": len(collections),
            "note": "On-disk JSON store. Development and demo use only.",
        }


# --------------------------------------------------------------------- helpers


def _encode_json(value: Any) -> Any:
    """Serialise types JSON does not handle natively.

    Datetimes are tagged rather than written as bare strings so they can be
    restored as datetimes on read. Without the tag, a timestamp would come back
    as a string and every comparison against it would silently be a string
    comparison.
    """
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "value"):  # enum
        return value.value
    raise TypeError(f"Cannot serialise {type(value).__name__} for the local store")


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        tag = value.get("__type__")
        if tag == "datetime":
            return datetime.fromisoformat(value["value"])
        if tag == "date":
            return date.fromisoformat(value["value"])
        return {key: _decode_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    return value


def _decode_document(document: dict[str, Any]) -> dict[str, Any]:
    return {key: _decode_value(value) for key, value in document.items()}


def _read_field(document: dict[str, Any], field: str) -> Any:
    """Read a possibly dotted field path, e.g. ``location.lat``."""
    current: Any = document
    for part in field.split("."):
        if not isinstance(current, dict):
            return _SENTINEL
        if part not in current:
            return _SENTINEL
        current = current[part]
    return current


def _compare(left: Any, right: Any, op: Operator) -> bool:
    """Apply one operator, treating incomparable types as non-matching.

    Firestore skips documents whose field type does not match the comparison;
    mirroring that keeps query results consistent across adapters instead of
    raising here and nowhere else.
    """
    if op is Operator.EQ:
        return bool(left == right)
    if op is Operator.NE:
        return bool(left != right)
    if op is Operator.IN:
        return isinstance(right, list | tuple | set) and left in right
    if op is Operator.NOT_IN:
        return isinstance(right, list | tuple | set) and left not in right
    if op is Operator.ARRAY_CONTAINS:
        return isinstance(left, list | tuple | set) and right in left

    try:
        if op is Operator.LT:
            return bool(left < right)
        if op is Operator.LTE:
            return bool(left <= right)
        if op is Operator.GT:
            return bool(left > right)
        if op is Operator.GTE:
            return bool(left >= right)
    except TypeError:
        return False
    return False


def _matches(document: dict[str, Any], filters: tuple[Filter, ...]) -> bool:
    for predicate in filters:
        value = _read_field(document, predicate.field)
        if value is _SENTINEL:
            # A document missing the field is not a match, which is also how
            # Firestore behaves.
            return False
        if not _compare(value, predicate.value, predicate.op):
            return False
    return True


class _SortKey:
    """Orders values of mixed types deterministically.

    A collection can legitimately hold documents where one has a null in the
    sort field. Python refuses to compare None with a string, so values are
    bucketed by type first and compared within the bucket.
    """

    __slots__ = ("_rank", "_value")

    def __init__(self, value: Any) -> None:
        if value is _SENTINEL or value is None:
            self._rank, self._value = 0, 0
        elif isinstance(value, bool):
            self._rank, self._value = 1, int(value)
        elif isinstance(value, int | float):
            self._rank, self._value = 2, float(value)
        elif isinstance(value, datetime):
            self._rank, self._value = 3, value.timestamp()
        elif isinstance(value, str):
            self._rank, self._value = 4, value
        else:
            self._rank, self._value = 5, str(value)

    def __lt__(self, other: _SortKey) -> bool:
        if self._rank != other._rank:
            return self._rank < other._rank
        return bool(self._value < other._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _SortKey):
            return NotImplemented
        return self._rank == other._rank and self._value == other._value


def _sort(documents: list[dict[str, Any]], orders: tuple[Order, ...]) -> None:
    if not orders:
        # Stable default so paging is repeatable rather than dependent on
        # dict ordering.
        documents.sort(key=lambda document: _SortKey(document.get("id")))
        return
    # Apply in reverse so the first declared order is the primary one.
    for order in reversed(orders):
        documents.sort(key=lambda document, f=order.field: _SortKey(_read_field(document, f)),
                       reverse=order.descending)


def _encode_cursor(document_id: str) -> str:
    return base64.urlsafe_b64encode(document_id.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _cursor_index(documents: list[dict[str, Any]], cursor: str | None) -> int:
    """Index just past the cursor document, or 0 when it is gone.

    A document can be deleted between pages. Restarting from the beginning is
    the safe choice: skipping the rest of the collection would silently hide
    records.
    """
    if not cursor:
        return 0
    target = _decode_cursor(cursor)
    if target is None:
        return 0
    for index, document in enumerate(documents):
        if str(document.get("id")) == target:
            return index + 1
    return 0
