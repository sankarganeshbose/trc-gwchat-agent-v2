from __future__ import annotations

import hashlib
import logging
import os
import sys

import structlog

_SALT = os.environ.get("TRC_AGENT_LOG_SALT", "dev-salt")


def ref(value: str | None) -> str | None:
    """Non-reversible reference for ids; logs never carry names, DOBs, free text or raw payloads."""
    return hashlib.sha256(f"{_SALT}:{value}".encode()).hexdigest()[:12] if value else None


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, structlog.processors.add_log_level,
                                    structlog.processors.TimeStamper(fmt="iso", utc=True), structlog.processors.JSONRenderer()],
                        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
                        cache_logger_on_first_use=True)


def get_logger(name: str = "trc_agent"):
    return structlog.get_logger(name)
