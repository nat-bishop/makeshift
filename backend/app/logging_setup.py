from __future__ import annotations

import logging

import structlog

from app.config import settings


def setup_logging() -> None:
    """Configure structlog with dev/prod renderer switching and stdlib bridge."""
    level = logging.getLevelName(settings.log_level.upper())

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.set_exc_info,
    ]

    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer()
        if settings.log_format == "console"
        else structlog.processors.JSONRenderer()
    )

    if settings.logfire_enabled:
        import logfire

        shared_processors.append(logfire.StructlogProcessor())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[*shared_processors, renderer],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler], force=True)

    for lib in ("httpx", "httpcore", "fal_client", "google.genai", "PIL"):
        logging.getLogger(lib).setLevel(logging.WARNING)
