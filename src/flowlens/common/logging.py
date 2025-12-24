"""Structured JSON logging using structlog.

Provides consistent logging configuration across all FlowLens services.
Supports both JSON (production) and console (development) formats.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from flowlens.common.config import LoggingSettings, get_settings


def add_service_context(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Add service context to log entries."""
    settings = get_settings()
    event_dict["service"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["environment"] = settings.environment
    return event_dict


def setup_logging(
    settings: LoggingSettings | None = None,
    service_name: str | None = None,
) -> None:
    """Configure structured logging for the application.

    Args:
        settings: Logging settings. Uses global settings if not provided.
        service_name: Optional service name to include in logs.
    """
    if settings is None:
        settings = get_settings().logging

    # Shared processors for all log entries
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.include_timestamp:
        shared_processors.insert(0, structlog.processors.TimeStamper(fmt="iso"))

    if settings.include_caller:
        shared_processors.append(structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            ]
        ))

    # Add service context
    shared_processors.append(add_service_context)

    # Format-specific processors
    if settings.format == "json":
        # JSON format for production
        format_processors: list[Processor] = [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Console format for development
        format_processors = [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.rich_traceback,
            ),
        ]

    # Configure structlog
    structlog.configure(
        processors=shared_processors + format_processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.level),
    )

    # Reduce noise from third-party loggers
    for logger_name in [
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy.engine",
        "asyncpg",
        "httpx",
        "httpcore",
    ]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str | None = None, **initial_context: Any) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance.

    Args:
        name: Logger name (usually __name__).
        **initial_context: Initial context to bind to the logger.

    Returns:
        Configured structlog logger.

    Example:
        logger = get_logger(__name__, request_id="abc123")
        logger.info("Processing request", user_id=42)
    """
    logger = structlog.get_logger(name)
    if initial_context:
        logger = logger.bind(**initial_context)
    return logger


class LoggerMixin:
    """Mixin class to add a logger to any class.

    Example:
        class MyService(LoggerMixin):
            def do_something(self):
                self.logger.info("Doing something")
    """

    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get logger bound to this class."""
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger


def bind_context(**context: Any) -> None:
    """Bind context variables for the current execution context.

    Context persists across async boundaries using contextvars.

    Args:
        **context: Key-value pairs to bind.

    Example:
        bind_context(request_id="abc123", user_id=42)
        logger.info("Request processed")  # Will include request_id and user_id
    """
    structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


def unbind_context(*keys: str) -> None:
    """Remove specific keys from the bound context.

    Args:
        *keys: Keys to remove from context.
    """
    structlog.contextvars.unbind_contextvars(*keys)
