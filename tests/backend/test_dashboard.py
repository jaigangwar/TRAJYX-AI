"""Overview KPIs and the shared event model.

The central assertion of this file is the honesty rule: a metric the platform
cannot compute is reported as unavailable with a reason, never as zero. "No
analysis has run" and "zero vehicles were detected" are different facts, and a
dashboard that shows 0 for both is lying to an operator.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tests.backend.conftest import auth_header
from trajyx_shared.domain import DataOrigin, EventType, ReportStatus, Role, Severity


def utc(**delta: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def make_camera(client: TestClient, token: str, name: str = "Cam A") -> dict:
    response = client.post(
        "/api/v1/cameras",
        headers=auth_header(token),
        json={"name": name, "location": {"latitude": 28.61, "longitude": 77.20}},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def seed_events(app, documents: list[dict]) -> None:
    """Write events straight through the store.

    The pipeline that would normally produce them does not exist until phase 4,
    and there is deliberately no client-facing event-creation endpoint — an
    open one would let a modified client fabricate a violation.
    """
    await app.state.store.bulk_create("risk_events", documents)


def event_document(
    event_type: EventType,
    *,
    camera_id: str | None = None,
    risk_score: float | None = None,
    origin: DataOrigin = DataOrigin.MEASURED,
    severity: Severity = Severity.INFO,
    confidence: float | None = 0.9,
    hours_ago: float = 1,
) -> dict:
    from trajyx_shared.domain import EVENT_CATEGORY

    return {
        "event_type": event_type.value,
        "category": EVENT_CATEGORY[event_type].value,
        "timestamp": datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        "camera_id": camera_id,
        "road_segment_id": None,
        "location": {"latitude": 28.61, "longitude": 77.20},
        "severity": severity.value,
        "confidence": confidence,
        "risk_score": risk_score,
        "origin": origin.value,
        "model_version": "test-1.0",
        "track_ids": [101, 102],
        "details": {},
        "review_status": ReportStatus.PENDING.value,
    }


class TestEmptyDashboard:
    def test_reports_unavailable_rather_than_zero(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token))
        assert response.status_code == 200

        body = response.json()
        vehicles = body["pipeline"]["vehicles_detected"]
        assert vehicles["available"] is False
        assert vehicles["value"] is None
        assert "phase 4" in vehicles["unavailable_reason"]

        average = body["risk"]["average_risk"]
        assert average["available"] is False
        assert average["value"] is None
        assert "phase 10" in average["unavailable_reason"]

    def test_counts_that_are_genuinely_zero_are_reported_as_zero(
        self, client: TestClient, admin_token: str
    ) -> None:
        """A camera count of zero is a fact, not missing data — the registry
        exists and is empty."""
        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        assert body["cameras"]["total"] == 0
        assert body["events"]["total"] == 0
        # videos_analysed is measurable (the collection exists), so it is 0.
        assert body["pipeline"]["videos_analysed"] == {
            "value": 0.0,
            "available": True,
            "unavailable_reason": None,
            "unit": None,
        }

    def test_reports_demo_mode(self, client: TestClient, admin_token: str) -> None:
        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        assert body["demo_mode"] is True

    def test_recent_events_is_empty_not_absent(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        assert body["recent_events"] == []


class TestCameraCounts:
    def test_counts_cameras_by_status(self, client: TestClient, admin_token: str) -> None:
        make_camera(client, admin_token, "Cam A")
        alerting = make_camera(client, admin_token, "Cam B")
        client.patch(
            f"/api/v1/cameras/{alerting['id']}",
            headers=auth_header(admin_token),
            json={"status": "ALERT"},
        )

        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        assert body["cameras"]["total"] == 2
        assert body["cameras"]["offline"] == 1
        assert body["cameras"]["alert"] == 1


class TestEventCounts:
    async def test_counts_events_by_category(self, client: TestClient, admin_token: str) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"]),
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
                event_document(EventType.HARD_BRAKING, camera_id=camera["id"]),
                event_document(EventType.NEAR_MISS, camera_id=camera["id"], risk_score=88.0),
                event_document(EventType.HAZARD_REPORT),
            ],
        )

        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        events = body["events"]
        assert events["total"] == 5
        assert events["violations"] == 2
        assert events["behaviour"] == 1
        assert events["interactions"] == 1
        assert events["reports"] == 1
        assert events["near_misses"] == 1
        assert events["critical"] == 1  # the 88.0 near miss

    async def test_the_window_excludes_older_events(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], hours_ago=2),
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], hours_ago=100),
            ],
        )

        recent = client.get(
            "/api/v1/dashboard/summary",
            headers=auth_header(admin_token),
            params={"window_hours": 24},
        ).json()
        assert recent["events"]["total"] == 1

        wider = client.get(
            "/api/v1/dashboard/summary",
            headers=auth_header(admin_token),
            params={"window_hours": 720},
        ).json()
        assert wider["events"]["total"] == 2

    async def test_demo_records_are_counted_separately(
        self, client: TestClient, admin_token: str
    ) -> None:
        """The total must stay auditable: an operator can see how much of it is
        synthetic."""
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
                event_document(
                    EventType.WRONG_WAY, camera_id=camera["id"], origin=DataOrigin.DEMO
                ),
                event_document(
                    EventType.NEAR_MISS, camera_id=camera["id"], origin=DataOrigin.DEMO
                ),
            ],
        )

        body = client.get("/api/v1/dashboard/summary", headers=auth_header(admin_token)).json()
        assert body["events"]["total"] == 3
        assert body["events"]["demo"] == 2


class TestEventList:
    async def test_returns_events_newest_first_with_camera_names(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = make_camera(client, admin_token, "Ring Road")
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], hours_ago=5),
                event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"], hours_ago=1),
            ],
        )

        response = client.get("/api/v1/events", headers=auth_header(admin_token))
        assert response.status_code == 200

        items = response.json()["items"]
        assert [item["event_type"] for item in items] == ["HELMET_VIOLATION", "WRONG_WAY"]
        # Denormalised so a table page needs no second request per row.
        assert items[0]["camera_name"] == "Ring Road"

    async def test_derives_category_and_risk_level(
        self, client: TestClient, admin_token: str
    ) -> None:
        """Both are derived, never stored twice: a stored copy could disagree
        with the event type or the score it came from."""
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [event_document(EventType.NEAR_MISS, camera_id=camera["id"], risk_score=62.0)],
        )

        item = client.get("/api/v1/events", headers=auth_header(admin_token)).json()["items"][0]
        assert item["category"] == "INTERACTION"
        assert item["risk_level"] == "HIGH"  # 51-75

    async def test_a_scoreless_event_has_no_risk_level(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app, [event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"])]
        )

        item = client.get("/api/v1/events", headers=auth_header(admin_token)).json()["items"][0]
        assert item["risk_score"] is None
        assert item["risk_level"] is None

    async def test_filters_by_event_type(self, client: TestClient, admin_token: str) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
                event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"]),
            ],
        )

        response = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"event_type": "WRONG_WAY"}
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["event_type"] == "WRONG_WAY"

    async def test_filters_by_category(self, client: TestClient, admin_token: str) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
                event_document(EventType.HARD_BRAKING, camera_id=camera["id"]),
            ],
        )

        response = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"category": "BEHAVIOR"}
        )
        assert [item["event_type"] for item in response.json()["items"]] == ["HARD_BRAKING"]

    async def test_origin_filter_excludes_demo_records(
        self, client: TestClient, admin_token: str
    ) -> None:
        """The honesty filter: an operator can ask for measured records only."""
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
                event_document(
                    EventType.WRONG_WAY, camera_id=camera["id"], origin=DataOrigin.DEMO
                ),
            ],
        )

        all_events = client.get("/api/v1/events", headers=auth_header(admin_token)).json()
        assert len(all_events["items"]) == 2

        measured = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"origin": "MEASURED"}
        ).json()
        assert len(measured["items"]) == 1
        assert measured["items"][0]["origin"] == "MEASURED"

    async def test_filters_by_minimum_confidence(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], confidence=0.42),
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], confidence=0.95),
            ],
        )

        response = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"min_confidence": 0.8}
        )
        assert len(response.json()["items"]) == 1

    async def test_pages_with_a_cursor(self, client: TestClient, admin_token: str) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.WRONG_WAY, camera_id=camera["id"], hours_ago=index + 1)
                for index in range(7)
            ],
        )

        first = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"limit": 3}
        ).json()
        assert len(first["items"]) == 3
        assert first["next_cursor"]

        second = client.get(
            "/api/v1/events",
            headers=auth_header(admin_token),
            params={"limit": 3, "cursor": first["next_cursor"]},
        ).json()
        first_ids = {item["id"] for item in first["items"]}
        second_ids = {item["id"] for item in second["items"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_reading_a_missing_event_is_a_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get("/api/v1/events/no-such-id", headers=auth_header(admin_token))
        assert response.status_code == 404


class TestEventReview:
    async def test_an_operator_can_confirm_a_violation(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        camera = make_camera(client, role_tokens[Role.ADMIN])
        await seed_events(
            client.app, [event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"])]
        )
        event_id = client.get(
            "/api/v1/events", headers=auth_header(role_tokens[Role.ADMIN])
        ).json()["items"][0]["id"]

        response = client.patch(
            f"/api/v1/events/{event_id}/review",
            headers=auth_header(role_tokens[Role.TRAFFIC_OPERATOR]),
            params={"status": ReportStatus.CONFIRMED.value},
        )
        assert response.status_code == 200
        assert response.json()["review_status"] == ReportStatus.CONFIRMED.value

    async def test_analysts_cannot_review(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        camera = make_camera(client, role_tokens[Role.ADMIN])
        await seed_events(
            client.app, [event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"])]
        )
        event_id = client.get(
            "/api/v1/events", headers=auth_header(role_tokens[Role.ADMIN])
        ).json()["items"][0]["id"]

        response = client.patch(
            f"/api/v1/events/{event_id}/review",
            headers=auth_header(role_tokens[Role.ANALYST]),
            params={"status": ReportStatus.CONFIRMED.value},
        )
        assert response.status_code == 403

    async def test_review_filter_finds_pending_items(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = make_camera(client, admin_token)
        await seed_events(
            client.app,
            [
                event_document(EventType.HELMET_VIOLATION, camera_id=camera["id"]),
                event_document(EventType.WRONG_WAY, camera_id=camera["id"]),
            ],
        )

        response = client.get(
            "/api/v1/events", headers=auth_header(admin_token), params={"review_status": "PENDING"}
        )
        assert len(response.json()["items"]) == 2


class TestPermissions:
    def test_drivers_cannot_read_events(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        """Privacy by design: a driver has no reason to read footage-derived
        detail about individual road users."""
        response = client.get("/api/v1/events", headers=auth_header(role_tokens[Role.DRIVER]))
        assert response.status_code == 403

    def test_drivers_cannot_read_the_dashboard(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get(
            "/api/v1/dashboard/summary", headers=auth_header(role_tokens[Role.DRIVER])
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST])
    def test_staff_can_read_the_dashboard(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        response = client.get(
            "/api/v1/dashboard/summary", headers=auth_header(role_tokens[role])
        )
        assert response.status_code == 200

    def test_there_is_no_public_event_creation_endpoint(
        self, client: TestClient, admin_token: str
    ) -> None:
        """Analysis output must not be client-writable: an open endpoint would
        let a modified client fabricate a violation."""
        response = client.post(
            "/api/v1/events",
            headers=auth_header(admin_token),
            json=event_document(EventType.WRONG_WAY) | {"timestamp": utc(hours=1)},
        )
        assert response.status_code == 405

    def test_unauthenticated_requests_are_rejected(self, client: TestClient) -> None:
        assert client.get("/api/v1/events").status_code == 401
        assert client.get("/api/v1/dashboard/summary").status_code == 401
        assert client.get("/api/v1/dashboard/camera-grid").status_code == 401


class TestCameraGrid:
    async def test_alerting_cameras_sort_first(
        self, client: TestClient, admin_token: str
    ) -> None:
        """An operator watching a wall display should never have to scroll to
        find the problem."""
        make_camera(client, admin_token, "AAA Quiet")
        alerting = make_camera(client, admin_token, "ZZZ Alerting")
        client.patch(
            f"/api/v1/cameras/{alerting['id']}",
            headers=auth_header(admin_token),
            json={"status": "ALERT"},
        )

        response = client.get("/api/v1/dashboard/camera-grid", headers=auth_header(admin_token))
        assert response.status_code == 200

        items = response.json()["items"]
        assert items[0]["name"] == "ZZZ Alerting"
        assert response.json()["total"] == 2
