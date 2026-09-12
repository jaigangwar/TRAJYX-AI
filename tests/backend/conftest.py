"""Shared fixtures for backend tests.

Tests run against the real application with the local adapters, not against
mocks. The point is to exercise the same authorisation code path production
uses: a fake auth provider in tests would leave the role checks that actually
protect CCTV data unverified.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import AuthBackend, DataBackend, Environment, Settings, StorageBackend
from app.main import create_app
from trajyx_shared.domain import Role

ADMIN_EMAIL = "admin@trajyx.test"
ADMIN_PASSWORD = "Bootstrap-Admin-1"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated, fully local configuration. Each test gets its own store."""
    return Settings(
        environment=Environment.TEST,
        data_backend=DataBackend.LOCAL,
        auth_backend=AuthBackend.LOCAL,
        storage_backend=StorageBackend.LOCAL,
        local_data_dir=tmp_path / "store",
        local_storage_dir=tmp_path / "storage",
        jwt_secret="test-only-secret-value-not-used-anywhere-else",
        # bcrypt's minimum cost. The suite creates dozens of accounts and the
        # work factor buys nothing here; Settings.startup_errors enforces a
        # floor of 10 for every non-test environment.
        bcrypt_rounds=4,
        demo_mode=True,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


# ---------------------------------------------------------------------- helpers


def bootstrap_admin(client: TestClient) -> dict:
    """Create the first administrator and return their profile."""
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "display_name": "Root"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, password: str) -> str:
    """Sign in and return the bearer token."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_user(
    client: TestClient, admin_token: str, email: str, role: Role, password: str = "Member-Pass-99"
) -> dict:
    """Create a user as an administrator and return the profile."""
    response = client.post(
        "/api/v1/users",
        headers=auth_header(admin_token),
        json={"email": email, "password": password, "role": role.value, "display_name": email},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def admin_token(client: TestClient) -> str:
    bootstrap_admin(client)
    return login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def role_tokens(client: TestClient, admin_token: str) -> dict[Role, str]:
    """A signed-in token for every role, for exhaustive permission tests."""
    tokens: dict[Role, str] = {Role.ADMIN: admin_token}

    for role in (Role.TRAFFIC_OPERATOR, Role.ANALYST, Role.DRIVER):
        email = f"{role.value.lower()}@trajyx.test"
        create_user(client, admin_token, email, role)
        tokens[role] = login(client, email, "Member-Pass-99")

    return tokens
