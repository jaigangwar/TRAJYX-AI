"""Local document store.

This adapter backs every development run and every test, so a bug here looks
like a bug somewhere else. It is also the reference for what the
:class:`DocumentStore` contract actually promises, which the Firestore adapter
must match.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.repositories.base import Filter, Operator, Query, utc_now
from app.repositories.local_store import LocalDocumentStore

COLLECTION = "cameras"


@pytest.fixture
def store(tmp_path: Path) -> LocalDocumentStore:
    return LocalDocumentStore(tmp_path / "store")


class TestCreateAndRead:
    async def test_create_assigns_an_id_and_returns_the_document(
        self, store: LocalDocumentStore
    ) -> None:
        created = await store.create(COLLECTION, {"name": "Junction 4", "status": "ONLINE"})

        assert created["id"]
        assert created["name"] == "Junction 4"

        fetched = await store.get(COLLECTION, created["id"])
        assert fetched == created

    async def test_create_honours_an_explicit_id(self, store: LocalDocumentStore) -> None:
        created = await store.create(COLLECTION, {"name": "A"}, document_id="cam-001")
        assert created["id"] == "cam-001"

    async def test_duplicate_explicit_id_is_a_conflict(self, store: LocalDocumentStore) -> None:
        await store.create(COLLECTION, {"name": "A"}, document_id="cam-001")
        with pytest.raises(ConflictError):
            await store.create(COLLECTION, {"name": "B"}, document_id="cam-001")

    async def test_get_returns_none_for_a_missing_document(self, store: LocalDocumentStore) -> None:
        assert await store.get(COLLECTION, "nope") is None

    async def test_get_on_a_collection_that_was_never_written(
        self, store: LocalDocumentStore
    ) -> None:
        assert await store.get("never_used", "x") is None
        assert (await store.query("never_used")).documents == []

    async def test_exists(self, store: LocalDocumentStore) -> None:
        created = await store.create(COLLECTION, {"name": "A"})
        assert await store.exists(COLLECTION, created["id"])
        assert not await store.exists(COLLECTION, "other")


class TestUpdate:
    async def test_update_merges_rather_than_replaces(self, store: LocalDocumentStore) -> None:
        created = await store.create(COLLECTION, {"name": "A", "status": "ONLINE", "lanes": 3})

        updated = await store.update(COLLECTION, created["id"], {"status": "OFFLINE"})

        assert updated["status"] == "OFFLINE"
        assert updated["name"] == "A"
        assert updated["lanes"] == 3

    async def test_update_of_a_missing_document_raises(self, store: LocalDocumentStore) -> None:
        """Update must never create: a typo in an id should fail loudly rather
        than produce a half-populated record."""
        with pytest.raises(NotFoundError):
            await store.update(COLLECTION, "nope", {"status": "OFFLINE"})

    async def test_update_cannot_rewrite_the_id(self, store: LocalDocumentStore) -> None:
        created = await store.create(COLLECTION, {"name": "A"})
        updated = await store.update(COLLECTION, created["id"], {"id": "hijacked"})
        assert updated["id"] == created["id"]
        assert await store.get(COLLECTION, "hijacked") is None


class TestDelete:
    async def test_delete_removes_the_document(self, store: LocalDocumentStore) -> None:
        created = await store.create(COLLECTION, {"name": "A"})
        await store.delete(COLLECTION, created["id"])
        assert await store.get(COLLECTION, created["id"]) is None

    async def test_deleting_a_missing_document_is_not_an_error(
        self, store: LocalDocumentStore
    ) -> None:
        await store.delete(COLLECTION, "never-existed")


class TestQuery:
    @pytest.fixture
    async def populated(self, store: LocalDocumentStore) -> LocalDocumentStore:
        for index, (name, status, risk) in enumerate(
            [
                ("Junction 1", "ONLINE", 12),
                ("Junction 2", "OFFLINE", 48),
                ("Junction 3", "ONLINE", 77),
                ("Junction 4", "ALERT", 91),
                ("Junction 5", "ONLINE", 33),
            ]
        ):
            await store.create(
                COLLECTION,
                {"name": name, "status": status, "risk_score": risk, "lanes": index + 1},
                document_id=f"cam-{index}",
            )
        return store

    async def test_returns_everything_with_no_filters(self, populated: LocalDocumentStore) -> None:
        assert len((await populated.query(COLLECTION)).documents) == 5

    async def test_equality_filter(self, populated: LocalDocumentStore) -> None:
        page = await populated.query(COLLECTION, Query().where(Filter.eq("status", "ONLINE")))
        assert len(page.documents) == 3

    async def test_comparison_filters(self, populated: LocalDocumentStore) -> None:
        page = await populated.query(COLLECTION, Query().where(Filter.gte("risk_score", 50)))
        assert {document["name"] for document in page.documents} == {"Junction 3", "Junction 4"}

    async def test_in_filter(self, populated: LocalDocumentStore) -> None:
        page = await populated.query(
            COLLECTION, Query().where(Filter.in_("status", ["OFFLINE", "ALERT"]))
        )
        assert len(page.documents) == 2

    async def test_filters_combine_as_and(self, populated: LocalDocumentStore) -> None:
        page = await populated.query(
            COLLECTION,
            Query().where(Filter.eq("status", "ONLINE"), Filter.gte("risk_score", 30)),
        )
        assert {document["name"] for document in page.documents} == {"Junction 3", "Junction 5"}

    async def test_a_document_missing_the_field_does_not_match(
        self, populated: LocalDocumentStore
    ) -> None:
        """Matches Firestore behaviour: a document without the field is skipped
        rather than treated as null."""
        await populated.create(COLLECTION, {"name": "No risk field"}, document_id="cam-x")
        page = await populated.query(COLLECTION, Query().where(Filter.gte("risk_score", 0)))
        assert "cam-x" not in {document["id"] for document in page.documents}

    async def test_ordering_ascending_and_descending(self, populated: LocalDocumentStore) -> None:
        ascending = await populated.query(COLLECTION, Query().order_by("risk_score"))
        assert [document["risk_score"] for document in ascending.documents] == [12, 33, 48, 77, 91]

        descending = await populated.query(
            COLLECTION, Query().order_by("risk_score", descending=True)
        )
        assert [document["risk_score"] for document in descending.documents] == [91, 77, 48, 33, 12]

    async def test_ordering_tolerates_a_missing_field(self, populated: LocalDocumentStore) -> None:
        """Python cannot compare None with int; the sort key must bucket by
        type rather than raise."""
        await populated.create(COLLECTION, {"name": "No score"}, document_id="cam-y")
        page = await populated.query(COLLECTION, Query().order_by("risk_score"))
        assert len(page.documents) == 6

    async def test_count_matches_the_filter(self, populated: LocalDocumentStore) -> None:
        assert await populated.count(COLLECTION) == 5
        assert await populated.count(COLLECTION, Query().where(Filter.eq("status", "ONLINE"))) == 3

    async def test_unsupported_comparison_does_not_raise(
        self, populated: LocalDocumentStore
    ) -> None:
        """Comparing a string field with a number must skip the document, not
        blow up mid-query."""
        page = await populated.query(COLLECTION, Query().where(Filter("name", Operator.GT, 5)))
        assert page.documents == []


class TestPaging:
    @pytest.fixture
    async def many(self, store: LocalDocumentStore) -> LocalDocumentStore:
        for index in range(12):
            await store.create(
                COLLECTION, {"seq": index}, document_id=f"doc-{index:02d}"
            )
        return store

    async def test_limit_returns_a_cursor(self, many: LocalDocumentStore) -> None:
        page = await many.query(COLLECTION, Query().order_by("seq").take(5))
        assert len(page.documents) == 5
        assert page.next_cursor

    async def test_cursor_continues_without_repeating(self, many: LocalDocumentStore) -> None:
        seen: list[int] = []
        cursor: str | None = None

        for _ in range(5):
            page = await many.query(COLLECTION, Query().order_by("seq").take(5).after(cursor))
            seen.extend(int(document["seq"]) for document in page.documents)
            cursor = page.next_cursor
            if cursor is None:
                break

        assert seen == list(range(12))

    async def test_last_page_has_no_cursor(self, many: LocalDocumentStore) -> None:
        page = await many.query(COLLECTION, Query().order_by("seq").take(20))
        assert len(page.documents) == 12
        assert page.next_cursor is None

    async def test_a_deleted_cursor_document_restarts_rather_than_skipping(
        self, many: LocalDocumentStore
    ) -> None:
        """Silently skipping the remainder would hide records; restarting is the
        safe failure."""
        first = await many.query(COLLECTION, Query().order_by("seq").take(5))
        assert first.next_cursor

        await many.delete(COLLECTION, "doc-04")

        resumed = await many.query(
            COLLECTION, Query().order_by("seq").take(5).after(first.next_cursor)
        )
        assert int(resumed.documents[0]["seq"]) == 0

    async def test_a_malformed_cursor_is_ignored(self, many: LocalDocumentStore) -> None:
        page = await many.query(COLLECTION, Query().order_by("seq").take(3).after("!!!not-base64"))
        assert int(page.documents[0]["seq"]) == 0


class TestTypeRoundTrip:
    async def test_datetimes_survive_as_datetimes(self, store: LocalDocumentStore) -> None:
        """A timestamp that came back as a string would make every later
        comparison a silent string comparison."""
        moment = utc_now()
        created = await store.create(COLLECTION, {"seen_at": moment})

        fetched = await store.get(COLLECTION, created["id"])
        assert isinstance(fetched["seen_at"], datetime)
        assert fetched["seen_at"] == moment
        assert fetched["seen_at"].tzinfo is not None

    async def test_datetime_comparison_filters_work_after_a_round_trip(
        self, store: LocalDocumentStore
    ) -> None:
        now = utc_now()
        await store.create(COLLECTION, {"name": "old", "seen_at": now - timedelta(days=2)})
        await store.create(COLLECTION, {"name": "new", "seen_at": now})

        page = await store.query(
            COLLECTION, Query().where(Filter.gte("seen_at", now - timedelta(hours=1)))
        )
        assert [document["name"] for document in page.documents] == ["new"]

    async def test_nested_structures_round_trip(self, store: LocalDocumentStore) -> None:
        payload = {
            "location": {"latitude": 28.61, "longitude": 77.20},
            "lanes": [{"index": 0, "heading": 90.0}, {"index": 1, "heading": 270.0}],
            "recorded_at": utc_now(),
        }
        created = await store.create(COLLECTION, payload)
        fetched = await store.get(COLLECTION, created["id"])

        assert fetched["location"]["latitude"] == 28.61
        assert fetched["lanes"][1]["heading"] == 270.0
        assert isinstance(fetched["recorded_at"], datetime)

    async def test_nested_dotted_field_filter(self, store: LocalDocumentStore) -> None:
        await store.create(COLLECTION, {"name": "A", "location": {"latitude": 28.61}})
        await store.create(COLLECTION, {"name": "B", "location": {"latitude": 12.97}})

        page = await store.query(
            COLLECTION, Query().where(Filter.gte("location.latitude", 20.0))
        )
        assert [document["name"] for document in page.documents] == ["A"]

    async def test_enum_values_are_stored_as_their_wire_value(
        self, store: LocalDocumentStore
    ) -> None:
        from trajyx_shared.domain import CameraStatus

        created = await store.create(COLLECTION, {"status": CameraStatus.ALERT})
        fetched = await store.get(COLLECTION, created["id"])
        assert fetched["status"] == "ALERT"


class TestBulkAndConcurrency:
    async def test_bulk_create_writes_everything(self, store: LocalDocumentStore) -> None:
        written = await store.bulk_create(
            "detections", [{"frame_index": index} for index in range(250)]
        )
        assert written == 250
        assert await store.count("detections") == 250

    async def test_bulk_create_of_nothing_is_a_no_op(self, store: LocalDocumentStore) -> None:
        assert await store.bulk_create("detections", []) == 0

    async def test_concurrent_creates_do_not_lose_writes(
        self, store: LocalDocumentStore
    ) -> None:
        """Reads and writes interleave on the event loop, so without the
        per-collection lock a read-modify-write would drop documents."""
        await asyncio.gather(
            *(store.create(COLLECTION, {"seq": index}) for index in range(40))
        )
        assert await store.count(COLLECTION) == 40

    async def test_writes_are_atomic_on_disk(self, store: LocalDocumentStore, tmp_path: Path) -> None:
        """Written via a temporary file plus os.replace, so a crash mid-write
        cannot leave a truncated collection."""
        await store.create(COLLECTION, {"name": "A"})
        leftovers = list((tmp_path / "store").glob("*.tmp"))
        assert leftovers == []


class TestSafety:
    @pytest.mark.parametrize("name", ["../escape", "sub/dir", "", ".", "..", "back\\slash"])
    async def test_rejects_collection_names_that_escape_the_root(
        self, store: LocalDocumentStore, name: str
    ) -> None:
        with pytest.raises(ValueError, match="Invalid collection name"):
            await store.get(name, "x")

    async def test_health_reports_the_backend_honestly(self, store: LocalDocumentStore) -> None:
        health = await store.health()
        assert health["backend"] == "local"
        assert health["writable"] is True
        # The degraded mode must be stated, not implied.
        assert "Development" in health["note"]


class TestUtcNow:
    def test_returns_an_aware_utc_datetime(self) -> None:
        """A naive timestamp silently breaks cross-deployment comparison."""
        now = utc_now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)
        assert abs((now - datetime.now(timezone.utc)).total_seconds()) < 5
