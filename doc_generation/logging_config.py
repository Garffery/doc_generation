from __future__ import annotations

import logging
import os

DEFAULT_LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
PACKAGE_LOGGER_NAME = "doc_generation"


def _resolve_log_level(level: str | None) -> int:
    name = (level or os.environ.get("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper()
    resolved = getattr(logging, name, None)
    if not isinstance(resolved, int):
        return logging.INFO
    return resolved


def configure_logging(level: str | None = None) -> None:
    """Configure application logging. Level can be set via LOG_LEVEL env var."""
    log_level = _resolve_log_level(level)

    logging.basicConfig(
        level=log_level,
        format=LOG_FORMAT,
        force=True,
    )
    logging.getLogger(PACKAGE_LOGGER_NAME).setLevel(log_level)
