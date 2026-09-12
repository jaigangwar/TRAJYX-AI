"""Phase 0 smoke tests: the app boots, routes resolve, errors are enveloped."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import AuthBackend, DataBackend, Environment, Settings
from app.main import create_app
from trajyx_shared.domain import CONTRACT_VERSION


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        environment=Environment.TEST,
        local_data_dir=tmp_path / "store",
        local_storage_dir=tmp_path / "storage",
        data_backend=DataBackend.LOCAL,
        auth_backend=AuthBackend.LOCAL,
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_root_advertises_api_prefix(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["api"] == "/api/v1"


def test_health_reports_resolved_capabilities(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["capabilities"]["data_backend"] == "local"
    assert body["capabilities"]["auth_backend"] == "local"


def test_health_surfaces_degraded_mode_as_warning(client: TestClient) -> None:
    """A local backend must never be silently presented as production-grade."""
    warnings = client.get("/api/v1/health").json()["warnings"]
    assert any("LOCAL" in warning for warning in warnings)


def test_liveness_is_dependency_free(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "trace-abc"})
    assert response.headers["X-Request-ID"] == "trace-abc"


def test_request_id_is_generated_when_absent(client: TestClient) -> None:
    assert client.get("/api/v1/health").headers.get("X-Request-ID")


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404

    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"]


def test_security_headers_are_present(client: TestClient) -> None:
    headers = client.get("/api/v1/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"


def test_production_rejects_default_jwt_secret() -> None:
    """Boot must fail loudly rather than run production on a dev secret."""
    unsafe = Settings(
        environment=Environment.PRODUCTION,
        data_backend=DataBackend.FIRESTORE,
        auth_backend=AuthBackend.FIREBASE,
    )
    with pytest.raises(RuntimeError, match="Invalid configuration"), TestClient(create_app(unsafe)):
        pass


def test_production_rejects_local_backends() -> None:
    unsafe = Settings(
        environment=Environment.PRODUCTION,
        jwt_secret="a-genuinely-unique-production-secret-value",
        data_backend=DataBackend.LOCAL,
        auth_backend=AuthBackend.LOCAL,
    )
    errors = unsafe.startup_errors()
    assert any("Local auth backend" in error for error in errors)
    assert any("Local data backend" in error for error in errors)
