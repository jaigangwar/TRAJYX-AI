"""Service health and capability reporting.

`/health` is intentionally honest: it reports which adapters actually resolved
so an operator can tell at a glance whether they are looking at Firebase-backed
data or the local development store.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from trajyx_shared.domain import CONTRACT_VERSION

from app.core.config import Settings, get_settings

router = APIRouter(tags=["system"])


class Capabilities(BaseModel):
    """Which adapter backs each subsystem, after `auto` resolution."""

    data_backend: str = Field(description="firestore | local")
    auth_backend: str = Field(description="firebase | local")
    storage_backend: str = Field(description="firebase | local")
    demo_mode: bool


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
    contract_version: str
    capabilities: Capabilities
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal configuration notes, surfaced so degraded modes are visible.",
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health and resolved capabilities",
)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        contract_version=CONTRACT_VERSION,
        capabilities=Capabilities(
            data_backend=settings.resolved_data_backend.value,
            auth_backend=settings.resolved_auth_backend.value,
            storage_backend=settings.resolved_storage_backend.value,
            demo_mode=settings.demo_mode,
        ),
        warnings=settings.startup_warnings(),
    )


@router.get(
    "/health/live",
    summary="Liveness probe",
    response_model=dict[str, str],
)
async def liveness() -> dict[str, str]:
    """Cheap probe for orchestrators. Never touches a downstream dependency."""
    return {"status": "ok"}
