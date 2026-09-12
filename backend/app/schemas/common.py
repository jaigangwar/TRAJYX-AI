"""Schema building blocks shared across the API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator
from trajyx_shared.domain import DataOrigin

from app.schemas.email import EmailAddress  # re-exported for convenience

__all__ = [
    "Acknowledgement",
    "ApiModel",
    "EmailAddress",
    "GeoPoint",
    "Page",
    "Provenance",
    "ResponseModel",
    "TimeRange",
]

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for every request and response model.

    ``extra="forbid"`` on requests turns a typo in a client payload into a 422
    naming the field, instead of a silently ignored value. That matters most
    for the alert-threshold settings, where an ignored field means a driver
    quietly gets the wrong warning distance.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ResponseModel(BaseModel):
    """Base for responses, which tolerate extra fields for forward compatibility."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class GeoPoint(ApiModel):
    """A WGS-84 coordinate.

    Field names match Firestore's ``GeoPoint`` so conversion is mechanical.
    """

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class Page(ResponseModel, Generic[T]):
    """A page of results.

    Cursor-based rather than offset-based: offsets get slower as a collection
    grows and Firestore cannot serve them at all.
    """

    items: list[T]
    next_cursor: str | None = Field(
        default=None,
        description="Pass as `cursor` to fetch the next page. Null means this is the last page.",
    )
    total: int | None = Field(
        default=None,
        description=(
            "Total matching records. Null when a count was not requested, since "
            "counting is a separate billed operation."
        ),
    )


class Provenance(ResponseModel):
    """How a value came to exist.

    Attached to anything derived rather than directly observed, so no consumer
    has to guess whether a number was measured, modelled or simulated.
    """

    origin: DataOrigin
    model_version: str | None = Field(
        default=None, description="Model that produced this value, when one did."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Model confidence, where the producer reports one."
    )


class TimeRange(ApiModel):
    """An inclusive-start, exclusive-end time window."""

    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: datetime, info) -> datetime:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise ValueError("end must be after start")
        return end


class Acknowledgement(ResponseModel):
    """Response for an action with no payload of its own."""

    ok: bool = True
    message: str | None = None
