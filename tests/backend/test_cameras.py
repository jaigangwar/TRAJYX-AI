"""Camera registry: CRUD, permissions, and capability derivation.

Capability derivation is the part that matters most. A camera without a stop
line cannot produce a red-light violation, and reporting that capability as
available would make an absence of events look like an absence of violations.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.backend.conftest import auth_header
from trajyx_shared.domain import CameraStatus, Role, SignalState

JUNCTION = {
    "name": "Ring Road / Sector 12",
    "location": {"latitude": 28.6139, "longitude": 77.2090},
    "road_name": "Outer Ring Road",
    "frame_width": 1920,
    "frame_height": 1080,
    "frame_rate": 25.0,
}


def create_camera(client: TestClient, token: str, **overrides: object) -> dict:
    response = client.post(
        "/api/v1/cameras", headers=auth_header(token), json={**JUNCTION, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestRegistration:
    def test_registers_a_camera_as_offline(self, client: TestClient, admin_token: str) -> None:
        """Claiming ONLINE before a frame has arrived would put a fabricated
        status on the monitoring grid."""
        camera = create_camera(client, admin_token)
        assert camera["status"] == CameraStatus.OFFLINE.value
        assert camera["signal_state"] == SignalState.UNKNOWN.value
        assert camera["current_risk_score"] is None
        assert camera["current_risk_level"] is None

    def test_rejects_a_duplicate_name(self, client: TestClient, admin_token: str) -> None:
        create_camera(client, admin_token)
        response = client.post("/api/v1/cameras", headers=auth_header(admin_token), json=JUNCTION)
        assert response.status_code == 409

    def test_rejects_an_out_of_range_coordinate(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/v1/cameras",
            headers=auth_header(admin_token),
            json={**JUNCTION, "location": {"latitude": 120.0, "longitude": 77.0}},
        )
        assert response.status_code == 422

    def test_rejects_duplicate_lane_indexes(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/v1/cameras",
            headers=auth_header(admin_token),
            json={
                **JUNCTION,
                "lane_directions": [
                    {"lane_index": 0, "heading_deg": 90},
                    {"lane_index": 0, "heading_deg": 270},
                ],
            },
        )
        assert response.status_code == 422

    def test_rejects_an_out_of_range_heading(self, client: TestClient, admin_token: str) -> None:
        # Headings are [0, 360); 360 is the same direction as 0 and must not
        # be accepted as a distinct value.
        response = client.post(
            "/api/v1/cameras",
            headers=auth_header(admin_token),
            json={**JUNCTION, "lane_directions": [{"lane_index": 0, "heading_deg": 360}]},
        )
        assert response.status_code == 422


class TestCapabilities:
    def test_a_bare_camera_can_do_none_of_the_geometry_checks(
        self, client: TestClient, admin_token: str
    ) -> None:
        capabilities = create_camera(client, admin_token)["capabilities"]
        assert capabilities == {
            "speed_estimation": False,
            "wrong_way_detection": False,
            "stop_line_violation": False,
            "red_light_violation": False,
        }

    def test_calibration_enables_speed_estimation(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(
            client,
            admin_token,
            calibration={"metres_per_pixel_at_reference": 0.08, "reference_y": 720.0},
        )
        assert camera["capabilities"]["speed_estimation"] is True

    def test_lane_directions_enable_wrong_way_detection(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(
            client,
            admin_token,
            lane_directions=[
                {"lane_index": 0, "heading_deg": 90.0, "label": "Eastbound"},
                {"lane_index": 1, "heading_deg": 270.0, "label": "Westbound"},
            ],
        )
        assert camera["capabilities"]["wrong_way_detection"] is True
        assert len(camera["lane_directions"]) == 2

    def test_a_stop_line_alone_does_not_enable_red_light_detection(
        self, client: TestClient, admin_token: str
    ) -> None:
        """Signal phase is still UNKNOWN, so a red-light violation cannot be
        asserted without inventing the phase."""
        camera = create_camera(
            client,
            admin_token,
            stop_line={"start": {"x": 200, "y": 800}, "end": {"x": 1700, "y": 780}},
        )
        assert camera["capabilities"]["stop_line_violation"] is True
        assert camera["capabilities"]["red_light_violation"] is False

    def test_a_stop_line_plus_a_known_phase_enables_red_light_detection(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(
            client,
            admin_token,
            stop_line={"start": {"x": 200, "y": 800}, "end": {"x": 1700, "y": 780}},
            signal_state=SignalState.RED.value,
        )
        assert camera["capabilities"]["red_light_violation"] is True

    def test_capabilities_follow_a_configuration_edit(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(client, admin_token)
        assert camera["capabilities"]["speed_estimation"] is False

        updated = client.patch(
            f"/api/v1/cameras/{camera['id']}",
            headers=auth_header(admin_token),
            json={"calibration": {"metres_per_pixel_at_reference": 0.05, "reference_y": 640.0}},
        )
        assert updated.status_code == 200
        assert updated.json()["capabilities"]["speed_estimation"] is True


class TestReadAndUpdate:
    def test_lists_cameras_by_name(self, client: TestClient, admin_token: str) -> None:
        create_camera(client, admin_token, name="Zebra Crossing")
        create_camera(client, admin_token, name="Alpha Junction")

        response = client.get("/api/v1/cameras", headers=auth_header(admin_token))
        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert names == sorted(names)

    def test_filters_by_status(self, client: TestClient, admin_token: str) -> None:
        create_camera(client, admin_token, name="One")
        second = create_camera(client, admin_token, name="Two")
        client.patch(
            f"/api/v1/cameras/{second['id']}",
            headers=auth_header(admin_token),
            json={"status": CameraStatus.ALERT.value},
        )

        response = client.get(
            "/api/v1/cameras",
            headers=auth_header(admin_token),
            params={"status": CameraStatus.ALERT.value},
        )
        assert [item["name"] for item in response.json()["items"]] == ["Two"]

    def test_partial_update_leaves_other_fields_alone(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(client, admin_token)
        response = client.patch(
            f"/api/v1/cameras/{camera['id']}",
            headers=auth_header(admin_token),
            json={"description": "Northbound approach"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "Northbound approach"
        assert body["name"] == JUNCTION["name"]
        assert body["frame_width"] == 1920

    def test_rename_onto_an_existing_name_is_a_conflict(
        self, client: TestClient, admin_token: str
    ) -> None:
        create_camera(client, admin_token, name="First")
        second = create_camera(client, admin_token, name="Second")

        response = client.patch(
            f"/api/v1/cameras/{second['id']}",
            headers=auth_header(admin_token),
            json={"name": "First"},
        )
        assert response.status_code == 409

    def test_renaming_to_its_own_name_is_allowed(
        self, client: TestClient, admin_token: str
    ) -> None:
        camera = create_camera(client, admin_token, name="Same")
        response = client.patch(
            f"/api/v1/cameras/{camera['id']}",
            headers=auth_header(admin_token),
            json={"name": "Same", "description": "unchanged name"},
        )
        assert response.status_code == 200

    def test_updating_a_missing_camera_is_a_404(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/cameras/no-such-id",
            headers=auth_header(admin_token),
            json={"description": "x"},
        )
        assert response.status_code == 404

    def test_delete_removes_it(self, client: TestClient, admin_token: str) -> None:
        camera = create_camera(client, admin_token)
        assert (
            client.delete(
                f"/api/v1/cameras/{camera['id']}", headers=auth_header(admin_token)
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/cameras/{camera['id']}", headers=auth_header(admin_token)
            ).status_code
            == 404
        )


class TestPermissions:
    @pytest.mark.parametrize("role", [Role.ANALYST, Role.DRIVER])
    def test_only_operators_and_admins_may_register(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        response = client.post(
            "/api/v1/cameras", headers=auth_header(role_tokens[role]), json=JUNCTION
        )
        assert response.status_code == 403

    def test_operators_may_register(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.post(
            "/api/v1/cameras",
            headers=auth_header(role_tokens[Role.TRAFFIC_OPERATOR]),
            json=JUNCTION,
        )
        assert response.status_code == 201

    def test_analysts_may_read_but_not_write(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        create_camera(client, role_tokens[Role.ADMIN])

        assert (
            client.get("/api/v1/cameras", headers=auth_header(role_tokens[Role.ANALYST])).status_code
            == 200
        )

    def test_drivers_cannot_read_the_registry(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        response = client.get("/api/v1/cameras", headers=auth_header(role_tokens[Role.DRIVER]))
        assert response.status_code == 403

    def test_unauthenticated_requests_are_rejected(self, client: TestClient) -> None:
        assert client.get("/api/v1/cameras").status_code == 401
        assert client.post("/api/v1/cameras", json=JUNCTION).status_code == 401
