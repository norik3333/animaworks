# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Centralized logging configuration for AnimaWorks.

Provides:
- RequestIdFilter: contextvars-based request ID injection into all log records
- JsonFormatter: JSONL file output for machine parsing
- setup_logging(): one-call configuration for console + file handlers
"""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


def set_request_id(request_id: str) -> None:
    """Set the current request ID (flows automatically through async calls)."""
    _request_id_var.set(request_id)


def get_request_id() -> str:
    """Get the current request ID."""
    return _request_id_var.get()


class RequestIdFilter(logging.Filter):
    """Inject request_id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()  # type: ignore[attr-defined]
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON (JSONL)."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    log_dir: Path | None = None,
    json_file: bool = True,
) -> None:
    """Configure logging for the entire AnimaWorks process.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, etc.).
        log_dir: Directory for log files. If None, file logging is disabled.
        json_file: Whether to use JSON format for the file handler.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers (replaces basicConfig)
    root.handlers.clear()

    req_filter = RequestIdFilter()

    # Console handler: human-readable
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    console.addFilter(req_filter)
    root.addHandler(console)

    # File handler: rotated, optionally JSON
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "animaworks.log"
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        if json_file:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s",
                )
            )
        file_handler.addFilter(req_filter)
        root.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)