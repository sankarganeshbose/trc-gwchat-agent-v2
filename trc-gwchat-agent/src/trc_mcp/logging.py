"""Structured JSON logging with PHI-safe helpers. Never log names, DOBs or free-text clinical content."""
from __future__ import annotations

import hashlib
import logging
import os
import sys

import structlog

_SALT = os.environ.get("TRC_MCP_LOG_SALT", "dev-salt")


def phi_ref(value: str | None) -> str | None:
    """Stable, non-reversible reference for member/provider ids so logs can be correlated without PHI."""
    if not value:
        return None
    return hashlib.sha256(f"{_SALT}:{value}".encode()).hexdigest()[:12]


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(stream=sys.stdout, level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "trc_mcp"):
    return structlog.get_logger(name)
