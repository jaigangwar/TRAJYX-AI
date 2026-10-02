"""Aggregate road-safety analytics.

One endpoint serves the whole Analytics page. Splitting it per chart would
mean re-reading the same window of events for every panel, and would let two
panels on one screen disagree about the window they describe.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import SettingsDep, StoreDep, require_staff
from app.schemas.analytics import AnalyticsResponse
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get(
    "/summary",
    response_model=AnalyticsResponse,
    summary="Aggregate analytics for a rolling window",
    dependencies=[Depends(require_staff)],
)
async def analytics_summary(
    store: StoreDep,
    settings: SettingsDep,
    window_hours: Annotated[
        int, Query(ge=1, le=2160, description="Rolling window, in hours. Up to 90 days.")
    ] = 168,
) -> AnalyticsResponse:
    return await AnalyticsService(store).compute(window_hours, demo_mode=settings.demo_mode)
