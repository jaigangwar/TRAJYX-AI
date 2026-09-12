"""Application error taxonomy and FastAPI exception handlers.

Every failure leaving the API uses one envelope so the web and mobile clients
can render errors uniformly:

    {"error": {"code": "NOT_FOUND", "message": "...", "details": {...},
               "request_id": "..."}}
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)


class TrajyxError(Exception):
    """Base class for expected, client-reportable failures."""

    code = "INTERNAL_ERROR"
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(TrajyxError):
    code = "NOT_FOUND"
    http_status = status.HTTP_404_NOT_FOUND


class ValidationError(TrajyxError):
    code = "VALIDATION_ERROR"
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


class AuthenticationError(TrajyxError):
    code = "UNAUTHENTICATED"
    http_status = status.HTTP_401_UNAUTHORIZED


class AuthorizationError(TrajyxError):
    code = "FORBIDDEN"
    http_status = status.HTTP_403_FORBIDDEN


class ConflictError(TrajyxError):
    code = "CONFLICT"
    http_status = status.HTTP_409_CONFLICT


class PayloadTooLargeError(TrajyxError):
    code = "PAYLOAD_TOO_LARGE"
    http_status = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


class UnsupportedMediaError(TrajyxError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


class DependencyUnavailableError(TrajyxError):
    """A required capability (model weights, Firebase, worker) is unavailable.

    Raised instead of silently degrading, so callers never mistake a missing
    capability for a genuine negative result.
    """

    code = "DEPENDENCY_UNAVAILABLE"
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE


def _envelope(
    code: str,
    message: str,
    request_id: str | None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    if request_id:
        payload["request_id"] = request_id
    return {"error": payload}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that normalise every error into the shared envelope."""

    @app.exception_handler(TrajyxError)
    async def _handle_trajyx(request: Request, exc: TrajyxError) -> JSONResponse:
        log.warning(
            "request.failed",
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            details=exc.details or None,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=_envelope(exc.code, exc.message, _request_id(request), exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                "VALIDATION_ERROR",
                "Request payload failed validation.",
                _request_id(request),
                {"issues": exc.errors()},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "UNAUTHENTICATED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
            429: "RATE_LIMITED",
        }.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail), _request_id(request)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback but never leak internals to the client.
        log.exception("request.unhandled", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(
                "INTERNAL_ERROR",
                "An unexpected error occurred. The incident has been logged.",
                _request_id(request),
            ),
        )
