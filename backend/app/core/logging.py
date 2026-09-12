"""Structured logging setup.

Development renders human-readable console lines; staging and production emit
JSON so logs are queryable. A request-scoped `request_id` is bound to the
context so every log line emitted while handling a request carries it.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Install structlog processors and align stdlib logging with them."""
    level = getattr(logging, settings.log_level, logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Any
    if settings.log_json:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    # Emit through stdlib logging so uvicorn, firebase-admin and shapely share
    # one sink and one format. This also gives `add_logger_name` a real
    # stdlib logger to read `.name` from.
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=level, force=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    for noisy in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for a module. Use `__name__` at call sites."""
    return structlog.get_logger(name)
