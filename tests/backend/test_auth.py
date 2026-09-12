"""Authentication behaviour: sign-in, sessions, provisioning, privilege boundaries."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.backend.conftest import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    auth_header,
    bootstrap_admin,
    create_user,
    login,
)
from trajyx_shared.domain import Role


class TestBootstrap:
    def test_creates_the_first_administrator(self, client: TestClient) -> None:
        profile = bootstrap_admin(client)
        assert profile["role"] == Role.ADMIN.value
        assert profile["email"] == ADMIN_EMAIL
        assert profile["status"] == "active"

    def test_refuses_a_second_administrator(self, client: TestClient) -> None:
        """Otherwise the endpoint would be an unauthenticated admin factory."""
        bootstrap_admin(client)

        response = client.post(
            "/api/v1/auth/bootstrap-admin",
            json={"email": "second@trajyx.test", "password": "Another-Pass-1"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_never_returns_a_password_or_hash(self, client: TestClient) -> None:
        body = client.post(
            "/api/v1/auth/bootstrap-admin",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        ).text
        assert ADMIN_PASSWORD not in body
        assert "password" not in body.lower()


class TestLogin:
    def test_returns_a_usable_token_and_profile(self, client: TestClient) -> None:
        bootstrap_admin(client)

        response = client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200

        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["role"] == Role.ADMIN.value

        me = client.get("/api/v1/auth/me", headers=auth_header(body["access_token"]))
        assert me.status_code == 200
        assert me.json()["email"] == ADMIN_EMAIL

    def test_rejects_a_wrong_password(self, client: TestClient) -> None:
        bootstrap_admin(client)
        response = client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "definitely-wrong"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_does_not_reveal_whether_an_address_exists(self, client: TestClient) -> None:
        """A different message for unknown vs. wrong password would turn the
        login form into an account-enumeration oracle."""
        bootstrap_admin(client)

        unknown = client.post(
            "/api/v1/auth/login", json={"email": "nobody@trajyx.test", "password": "whatever-12"}
        )
        wrong = client.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "whatever-12"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]

    def test_email_is_case_insensitive(self, client: TestClient) -> None:
        bootstrap_admin(client)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200

    def test_rejects_a_malformed_email(self, client: TestClient) -> None:
        response = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_suspended_account_cannot_sign_in(self, client: TestClient, admin_token: str) -> None:
        user = create_user(client, admin_token, "suspendme@trajyx.test", Role.ANALYST)

        suspended = client.patch(
            f"/api/v1/users/{user['id']}/status",
            headers=auth_header(admin_token),
            json={"status": "suspended"},
        )
        assert suspended.status_code == 200

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "suspendme@trajyx.test", "password": "Member-Pass-99"},
        )
        assert response.status_code == 403
        assert "suspended" in response.json()["error"]["message"].lower()


class TestTokenVerification:
    def test_rejects_a_missing_token(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_rejects_a_garbage_token(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me", headers=auth_header("not.a.jwt"))
        assert response.status_code == 401

    def test_rejects_a_token_signed_with_another_key(self, client: TestClient) -> None:
        """A forged token must fail on signature, not be trusted for its claims."""
        from jose import jwt

        forged = jwt.encode(
            {"sub": "attacker", "role": Role.ADMIN.value, "iss": "trajyx-local"},
            "a-completely-different-secret",
            algorithm="HS256",
        )
        response = client.get("/api/v1/auth/me", headers=auth_header(forged))
        assert response.status_code == 401

    def test_rejects_a_non_bearer_scheme(self, client: TestClient) -> None:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Basic YWJjOjEyMw=="})
        assert response.status_code == 401

    def test_rejects_an_expired_token(self, client: TestClient, settings) -> None:
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
        expired = jwt.encode(
            {
                "sub": "someone",
                "role": Role.ADMIN.value,
                "iss": "trajyx-local",
                "exp": int(expired_at.timestamp()),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
        response = client.get("/api/v1/auth/me", headers=auth_header(expired))
        assert response.status_code == 401

    def test_a_role_change_takes_effect_on_the_next_request(
        self, client: TestClient, admin_token: str
    ) -> None:
        """The role is re-read from the store per request, so a demotion does
        not wait for the old token to expire."""
        user = create_user(client, admin_token, "promote@trajyx.test", Role.DRIVER)
        user_token = login(client, "promote@trajyx.test", "Member-Pass-99")

        assert client.get("/api/v1/auth/me", headers=auth_header(user_token)).json()["role"] == "DRIVER"

        client.patch(
            f"/api/v1/users/{user['id']}/role",
            headers=auth_header(admin_token),
            json={"role": Role.ANALYST.value},
        )

        # Same token, new role.
        refreshed = client.get("/api/v1/auth/me", headers=auth_header(user_token))
        assert refreshed.json()["role"] == Role.ANALYST.value

    def test_suspension_invalidates_an_existing_token(
        self, client: TestClient, admin_token: str
    ) -> None:
        user = create_user(client, admin_token, "revoke@trajyx.test", Role.ANALYST)
        user_token = login(client, "revoke@trajyx.test", "Member-Pass-99")
        assert client.get("/api/v1/auth/me", headers=auth_header(user_token)).status_code == 200

        client.patch(
            f"/api/v1/users/{user['id']}/status",
            headers=auth_header(admin_token),
            json={"status": "suspended"},
        )

        response = client.get("/api/v1/auth/me", headers=auth_header(user_token))
        assert response.status_code == 403


class TestRegistration:
    def test_public_registration_creates_a_driver(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "driver@trajyx.test", "password": "Driver-Pass-1", "display_name": "Dee"},
        )
        assert response.status_code == 201
        assert response.json()["role"] == Role.DRIVER.value

    def test_registration_cannot_request_a_privileged_role(self, client: TestClient) -> None:
        """The schema forbids unknown fields, so a role field is rejected
        outright rather than silently ignored."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "sneaky@trajyx.test",
                "password": "Sneaky-Pass-1",
                "role": Role.ADMIN.value,
            },
        )
        assert response.status_code == 422

    def test_duplicate_email_is_a_conflict(self, client: TestClient) -> None:
        payload = {"email": "dupe@trajyx.test", "password": "Dupe-Pass-11"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201

        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"

    @pytest.mark.parametrize("password", ["short", "alllowercase", "123456789012"])
    def test_weak_passwords_are_rejected(self, client: TestClient, password: str) -> None:
        response = client.post(
            "/api/v1/auth/register", json={"email": "weak@trajyx.test", "password": password}
        )
        assert response.status_code == 422

    def test_a_long_passphrase_is_accepted(self, client: TestClient) -> None:
        """Length should beat composition rules; a real passphrase must pass."""
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "phrase@trajyx.test", "password": "correct horse battery Staple"},
        )
        assert response.status_code == 201


class TestSelfService:
    def test_a_user_can_update_their_display_name(self, client: TestClient, admin_token: str) -> None:
        response = client.patch(
            "/api/v1/auth/me", headers=auth_header(admin_token), json={"display_name": "Renamed"}
        )
        assert response.status_code == 200
        assert response.json()["display_name"] == "Renamed"

    def test_a_user_cannot_change_their_own_role(self, client: TestClient, admin_token: str) -> None:
        """The clearest privilege-escalation attempt; the schema must refuse it."""
        create_user(client, admin_token, "climber@trajyx.test", Role.DRIVER)
        token = login(client, "climber@trajyx.test", "Member-Pass-99")

        response = client.patch(
            "/api/v1/auth/me", headers=auth_header(token), json={"role": Role.ADMIN.value}
        )
        assert response.status_code == 422
        assert client.get("/api/v1/auth/me", headers=auth_header(token)).json()["role"] == "DRIVER"

    def test_a_user_cannot_reactivate_their_own_suspended_account(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.patch(
            "/api/v1/auth/me", headers=auth_header(admin_token), json={"status": "active"}
        )
        assert response.status_code == 422


class TestPasswordChange:
    def test_changes_the_password_and_the_old_one_stops_working(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(admin_token),
            json={"current_password": ADMIN_PASSWORD, "new_password": "Rotated-Secret-7"},
        )
        assert response.status_code == 200

        assert (
            client.post(
                "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "Rotated-Secret-7"}
            ).status_code
            == 200
        )

    def test_requires_the_correct_current_password(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(admin_token),
            json={"current_password": "wrong-one", "new_password": "Rotated-Secret-7"},
        )
        assert response.status_code == 401

    def test_rejects_reusing_the_same_password(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            headers=auth_header(admin_token),
            json={"current_password": ADMIN_PASSWORD, "new_password": ADMIN_PASSWORD},
        )
        assert response.status_code == 422

    def test_requires_authentication(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "a", "new_password": "Whatever-12"},
        )
        assert response.status_code == 401
