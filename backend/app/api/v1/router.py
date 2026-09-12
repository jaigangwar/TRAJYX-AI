"""Version 1 API router.

Feature routers are mounted here as each phase lands, so the surface of the
API always matches what is actually implemented. Nothing is registered before
it works.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    cameras,
    dashboard,
    events,
    health,
    risk,
    users,
    videos,
)

api_router = APIRouter()

# Phase 0
api_router.include_router(health.router)

# Phase 1
api_router.include_router(auth.router)
api_router.include_router(users.router)

# Phase 2
api_router.include_router(dashboard.router)
api_router.include_router(cameras.router)
api_router.include_router(events.router)

# Phases 3-8: video analysis pipeline
api_router.include_router(videos.router)

# Phase 10: geospatial risk and driver alerts
api_router.include_router(risk.router)
