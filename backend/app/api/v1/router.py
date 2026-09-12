"""Version 1 API router.

Feature routers are mounted here as each phase lands, so the surface of the
API always matches what is actually implemented. Nothing is registered before
it works.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import auth, health, users

api_router = APIRouter()

# Phase 0
api_router.include_router(health.router)

# Phase 1
api_router.include_router(auth.router)
api_router.include_router(users.router)
