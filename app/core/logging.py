"""Structured logging configuration using structlog."""
import logging
import sys
import structlog
from app.core.config import get_settings


def configure_logging() -> None:
    """Configure structlog for structured JSON logging.

    Uses stdlib logging as the backend so processors like
    `add_logger_name` (which require a stdlib Logger) work correctly.
    """
    settings = get_settings()
    log_level = logging.DEBUG if settings.debug else logging.INFO

    # ── Configure stdlib root logger ──────────────────────────────────
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    logging.basicConfig(
        level=log_level,
        handlers=[handler],
        force=True,
    )

    # ── Configure structlog ───────────────────────────────────────────
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.debug:
        # Human-readable output in dev
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # JSON output in production
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
