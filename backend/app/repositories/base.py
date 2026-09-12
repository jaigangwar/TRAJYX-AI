"""Persistence abstraction.

Every read and write in TRAJYX goes through these interfaces. No route, service
or engine imports a Firestore client, which is what keeps the documented
migration to PostgreSQL + PostGIS a change of adapter rather than a rewrite.

The model is deliberately document-shaped — collection, document id, dict of
fields — because that is the intersection of what Firestore and a relational
store can both serve without contortion. Anything richer (joins, aggregate
pipelines) is expressed in the geo and analytics layers over plain
coordinates and values, so it can be pushed down to SQL later.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class Operator(str, Enum):
    """Query operators supported by every adapter.

    Restricted on purpose: this is the set Firestore can serve without a
    fan-out read, and that maps directly onto SQL. Adding an operator here
    means adding it to all adapters.
    """

    EQ = "=="
    NE = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    IN = "in"
    NOT_IN = "not-in"
    ARRAY_CONTAINS = "array-contains"


@dataclass(frozen=True, slots=True)
class Filter:
    """A single field predicate."""

    field: str
    op: Operator
    value: Any

    @staticmethod
    def eq(field: str, value: Any) -> Filter:
        return Filter(field, Operator.EQ, value)

    @staticmethod
    def gte(field: str, value: Any) -> Filter:
        return Filter(field, Operator.GTE, value)

    @staticmethod
    def lte(field: str, value: Any) -> Filter:
        return Filter(field, Operator.LTE, value)

    @staticmethod
    def in_(field: str, values: Sequence[Any]) -> Filter:
        return Filter(field, Operator.IN, list(values))


@dataclass(frozen=True, slots=True)
class Order:
    field: str
    descending: bool = False


@dataclass(frozen=True, slots=True)
class Query:
    """A read request against one collection.

    `cursor` is an opaque adapter-specific token. Offset paging is not offered:
    it degrades badly on large collections and Firestore does not support it
    natively, so exposing it would invite a query that works in development and
    fails in production.
    """

    filters: tuple[Filter, ...] = ()
    orders: tuple[Order, ...] = ()
    limit: int | None = None
    cursor: str | None = None

    def where(self, *filters: Filter) -> Query:
        return Query(self.filters + filters, self.orders, self.limit, self.cursor)

    def order_by(self, field: str, descending: bool = False) -> Query:
        return Query(self.filters, self.orders + (Order(field, descending),), self.limit, self.cursor)

    def take(self, limit: int) -> Query:
        return Query(self.filters, self.orders, limit, self.cursor)

    def after(self, cursor: str | None) -> Query:
        return Query(self.filters, self.orders, self.limit, cursor)


@dataclass(slots=True)
class Page:
    """One page of documents plus the cursor to continue from."""

    documents: list[dict[str, Any]]
    next_cursor: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.documents


class DocumentStore(abc.ABC):
    """A document database.

    Documents are plain dicts. Every document carries its own `id` field, so a
    result can be passed to a Pydantic schema without the caller needing to
    merge the key back in.

    Timestamps are stored as timezone-aware UTC `datetime`. Adapters are
    responsible for converting to and from their native representation, so no
    caller ever has to reason about Firestore's `DatetimeWithNanoseconds`.
    """

    @abc.abstractmethod
    async def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        """Return one document, or None when it does not exist."""

    @abc.abstractmethod
    async def create(
        self, collection: str, data: dict[str, Any], document_id: str | None = None
    ) -> dict[str, Any]:
        """Insert a document and return it, including its assigned `id`.

        Raises:
            ConflictError: if `document_id` is given and already exists.
        """

    @abc.abstractmethod
    async def update(self, collection: str, document_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Merge `data` into an existing document and return the result.

        Raises:
            NotFoundError: if the document does not exist. Update never
                creates, so a typo in an id fails loudly instead of silently
                producing a half-populated record.
        """

    @abc.abstractmethod
    async def delete(self, collection: str, document_id: str) -> None:
        """Remove a document. Deleting a missing document is not an error."""

    @abc.abstractmethod
    async def query(self, collection: str, query: Query | None = None) -> Page:
        """Return documents matching `query`."""

    @abc.abstractmethod
    async def count(self, collection: str, query: Query | None = None) -> int:
        """Count matching documents without transferring them."""

    @abc.abstractmethod
    async def bulk_create(self, collection: str, documents: Iterable[dict[str, Any]]) -> int:
        """Insert many documents, returning how many were written.

        Exists because the analysis pipeline writes detections and tracking
        events in the thousands; doing that one round trip at a time is the
        difference between seconds and minutes.
        """

    async def exists(self, collection: str, document_id: str) -> bool:
        return await self.get(collection, document_id) is not None

    @abc.abstractmethod
    async def health(self) -> dict[str, Any]:
        """Report reachability and identifying detail for /health."""

    async def close(self) -> None:
        """Release connections. Overridden where an adapter holds resources."""
        return


def utc_now() -> datetime:
    """Current time, timezone-aware UTC.

    Used instead of `datetime.utcnow()` (naive, deprecated) so every stored
    timestamp is unambiguous. Road-safety events are compared across
    deployments and time zones; a naive timestamp silently breaks that.
    """
    from datetime import timezone

    return datetime.now(timezone.utc)
