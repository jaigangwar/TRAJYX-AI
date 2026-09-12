"""Role authorisation, enforced server-side.

The dashboard hides sections a role cannot use, but hiding a menu item is not
access control. These tests drive the API directly, the way a hand-written
request would, and assert every role boundary holds.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.backend.conftest import auth_header, create_user, login
from trajyx_shared.domain import Role

#: Roles that may use the dashboard at all.
STAFF = (Role.ADMIN, Role.TRAFFIC_OPERATOR, Role.ANALYST)


class TestUserAdministration:
    @pytest.mark.parametrize("role", [Role.TRAFFIC_OPERATOR, Role.ANALYST, Role.DRIVER])
    def test_only_admins_can_list_users(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        response = client.get("/api/v1/users", headers=auth_header(role_tokens[role]))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_admins_can_list_users(self, client: TestClient, role_tokens: dict[Role, str]) -> None:
        response = client.get("/api/v1/users", headers=auth_header(role_tokens[Role.ADMIN]))
        assert response.status_code == 200
        assert len(response.json()["items"]) == 4

    @pytest.mark.parametrize("role", [Role.TRAFFIC_OPERATOR, Role.ANALYST, Role.DRIVER])
    def test_only_admins_can_create_users(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        """The critical boundary: if an operator could create users, they could
        create an administrator and escalate."""
        response = client.post(
            "/api/v1/users",
            headers=auth_header(role_tokens[role]),
            json={"email": "new@trajyx.test", "password": "Created-Pass-1", "role": "ADMIN"},
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("role", [Role.TRAFFIC_OPERATOR, Role.ANALYST, Role.DRIVER])
    def test_only_admins_can_change_a_role(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        target = create_user(client, role_tokens[Role.ADMIN], "target@trajyx.test", Role.DRIVER)
        response = client.patch(
            f"/api/v1/users/{target['id']}/role",
            headers=auth_header(role_tokens[role]),
            json={"role": Role.ADMIN.value},
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("role", [Role.TRAFFIC_OPERATOR, Role.ANALYST, Role.DRIVER])
    def test_only_admins_can_delete_a_user(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        target = create_user(client, role_tokens[Role.ADMIN], "deleteme@trajyx.test", Role.DRIVER)
        response = client.delete(
            f"/api/v1/users/{target['id']}", headers=auth_header(role_tokens[role])
        )
        assert response.status_code == 403

    def test_drivers_cannot_read_a_user_record(
        self, client: TestClient, role_tokens: dict[Role, str]
    ) -> None:
        """Staff can read user records to attribute events; a driver cannot."""
        target = create_user(client, role_tokens[Role.ADMIN], "someone@trajyx.test", Role.DRIVER)
        response = client.get(
            f"/api/v1/users/{target['id']}", headers=auth_header(role_tokens[Role.DRIVER])
        )
        assert response.status_code == 403

    @pytest.mark.parametrize("role", STAFF)
    def test_staff_can_read_a_user_record(
        self, client: TestClient, role_tokens: dict[Role, str], role: Role
    ) -> None:
        target = create_user(client, role_tokens[Role.ADMIN], "known@trajyx.test", Role.DRIVER)
        response = client.get(
            f"/api/v1/users/{target['id']}", headers=auth_header(role_tokens[role])
        )
        assert response.status_code == 200

    def test_unauthenticated_requests_are_rejected(self, client: TestClient) -> None:
        protected = [
            ("GET", "/api/v1/users", None),
            ("POST", "/api/v1/users", {}),
            ("GET", "/api/v1/users/anything", None),
            ("GET", "/api/v1/auth/me", None),
            ("PATCH", "/api/v1/auth/me", {}),
            ("PATCH", "/api/v1/users/anything/role", {"role": "ADMIN"}),
            ("PATCH", "/api/v1/users/anything/status", {"status": "suspended"}),
            ("DELETE", "/api/v1/users/anything", None),
            ("POST", "/api/v1/auth/logout", None),
        ]
        for method, path, body in protected:
            response = client.request(method, path, json=body)
            assert response.status_code == 401, f"{method} {path} was not protected"


class TestLastAdministratorProtection:
    """Losing the last administrator makes a deployment unadministrable, with
    no recovery short of direct database access."""

    def test_cannot_demote_the_only_administrator(
        self, client: TestClient, admin_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()

        response = client.patch(
            f"/api/v1/users/{me['id']}/role",
            headers=auth_header(admin_token),
            json={"role": Role.ANALYST.value},
        )
        assert response.status_code == 422
        assert "only administrator" in response.json()["error"]["message"]

    def test_can_demote_once_another_administrator_exists(
        self, client: TestClient, admin_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        create_user(client, admin_token, "second-admin@trajyx.test", Role.ADMIN)

        response = client.patch(
            f"/api/v1/users/{me['id']}/role",
            headers=auth_header(admin_token),
            json={"role": Role.ANALYST.value},
        )
        assert response.status_code == 200
        assert response.json()["role"] == Role.ANALYST.value

    def test_cannot_suspend_the_only_administrator(
        self, client: TestClient, admin_token: str
    ) -> None:
        me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        response = client.patch(
            f"/api/v1/users/{me['id']}/status",
            headers=auth_header(admin_token),
            json={"status": "suspended"},
        )
        assert response.status_code == 422

    def test_cannot_delete_own_account(self, client: TestClient, admin_token: str) -> None:
        me = client.get("/api/v1/auth/me", headers=auth_header(admin_token)).json()
        response = client.delete(f"/api/v1/users/{me['id']}", headers=auth_header(admin_token))
        assert response.status_code == 422


class TestAdministrativeActions:
    def test_admin_can_create_each_role(self, client: TestClient, admin_token: str) -> None:
        for role in Role:
            created = create_user(client, admin_token, f"made-{role.value.lower()}@trajyx.test", role)
            assert created["role"] == role.value

    def test_created_user_can_sign_in_with_their_role(
        self, client: TestClient, admin_token: str
    ) -> None:
        create_user(client, admin_token, "operator2@trajyx.test", Role.TRAFFIC_OPERATOR)
        token = login(client, "operator2@trajyx.test", "Member-Pass-99")

        me = client.get("/api/v1/auth/me", headers=auth_header(token))
        assert me.json()["role"] == Role.TRAFFIC_OPERATOR.value

    def test_role_filter_narrows_the_listing(self, client: TestClient, admin_token: str) -> None:
        create_user(client, admin_token, "d1@trajyx.test", Role.DRIVER)
        create_user(client, admin_token, "d2@trajyx.test", Role.DRIVER)

        response = client.get(
            "/api/v1/users", headers=auth_header(admin_token), params={"role": Role.DRIVER.value}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        assert {item["role"] for item in items} == {Role.DRIVER.value}

    def test_deleted_user_cannot_sign_in(self, client: TestClient, admin_token: str) -> None:
        target = create_user(client, admin_token, "gone@trajyx.test", Role.DRIVER)
        assert (
            client.delete(
                f"/api/v1/users/{target['id']}", headers=auth_header(admin_token)
            ).status_code
            == 200
        )

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "gone@trajyx.test", "password": "Member-Pass-99"},
        )
        assert response.status_code == 401

    def test_reading_a_missing_user_is_a_404(self, client: TestClient, admin_token: str) -> None:
        response = client.get("/api/v1/users/no-such-id", headers=auth_header(admin_token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"


class TestErrorResponseHygiene:
    def test_a_validation_error_never_echoes_the_submitted_password(
        self, client: TestClient
    ) -> None:
        """Regression test.

        Pydantic includes the offending ``input`` in each validation error. An
        earlier version passed that list straight into the response, so a
        rejected registration echoed the caller's password back in the 422
        body — and into any log that records response bodies.
        """
        secret = "lowercaseonly"  # rejected: single character class
        response = client.post(
            "/api/v1/auth/register", json={"email": "leak@trajyx.test", "password": secret}
        )

        assert response.status_code == 422
        assert secret not in response.text

        issues = response.json()["error"]["details"]["issues"]
        assert any(issue["field"] == "password" for issue in issues)
        # Only these three keys, so a future field cannot reintroduce the leak.
        for issue in issues:
            assert set(issue) == {"field", "message", "type"}

    def test_a_custom_validator_failure_returns_422_not_500(self, client: TestClient) -> None:
        """Regression test.

        For a custom validator Pydantic puts the original exception object in
        ``ctx``. Serialising it raised ``TypeError`` inside the error handler,
        turning a client mistake into a 500.
        """
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "not a valid address", "password": "Fine-Password-1"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_error_responses_carry_a_request_id(self, client: TestClient) -> None:
        response = client.get("/api/v1/users", headers=auth_header("bogus"))
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]

    def test_internal_details_are_not_leaked(self, client: TestClient, admin_token: str) -> None:
        """A 404 must not reveal the storage layout or a filesystem path."""
        body = client.get("/api/v1/users/../../etc/passwd", headers=auth_header(admin_token)).text
        assert "Traceback" not in body
        assert "local_store" not in body
