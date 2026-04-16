"""Structured JSON logging via ``structlog``.

Every log line is JSON and carries contextual fields bound by middleware:
``trace_id``, ``user_id``, ``account_id``, ``correlation_id``.

Do not use ``print`` or the stdlib ``logging`` module directly elsewhere —
always go through :func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.stdlib import BoundLogger


def configure_logging(level: str = "INFO", env: str = "development") -> None:
    """Configure structlog + stdlib logging to emit JSON to stdout."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a bound structlog logger."""
    return structlog.stdlib.get_logger(name)


def bind_request_context(
    *,
    trace_id: str | None = None,
    user_id: str | None = None,
    account_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Bind per-request context so every log line in this async scope includes it."""
    bindings: dict[str, str] = {}
    if trace_id:
        bindings["trace_id"] = trace_id
    if user_id:
        bindings["user_id"] = user_id
    if account_id:
        bindings["account_id"] = account_id
    if correlation_id:
        bindings["correlation_id"] = correlation_id
    if bindings:
        structlog.contextvars.bind_contextvars(**bindings)
