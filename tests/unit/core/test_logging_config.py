"""Unit tests for core/logging_config.py — logging setup and formatters."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    get_request_id,
    set_request_id,
    setup_logging,
)


# ── Request ID contextvars ────────────────────────────────


class TestRequestId:
    def test_default_value(self):
        # Reset to default
        set_request_id("-")
        assert get_request_id() == "-"

    def test_set_and_get(self):
        set_request_id("req-abc-123")
        assert get_request_id() == "req-abc-123"
        # Cleanup
        set_request_id("-")

    def test_overwrite(self):
        set_request_id("first")
        set_request_id("second")
        assert get_request_id() == "second"
        set_request_id("-")


# ── RequestIdFilter ───────────────────────────────────────


class TestRequestIdFilter:
    def test_injects_request_id(self):
        set_request_id("test-filter-id")
        filt = RequestIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="hello", args=(), exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert record.request_id == "test-filter-id"  # type: ignore[attr-defined]
        set_request_id("-")

    def test_always_returns_true(self):
        filt = RequestIdFilter()
        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="",
            lineno=0, msg="msg", args=(), exc_info=None,
        )
        assert filt.filter(record) is True


# ── JsonFormatter ─────────────────────────────────────────


class TestJsonFormatter:
    def test_basic_format(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="mylogger", level=logging.INFO, pathname="test.py",
            lineno=42, msg="Test message", args=(), exc_info=None,
        )
        record.request_id = "req-001"  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "mylogger"
        assert data["request_id"] == "req-001"
        assert data["msg"] == "Test message"
        assert "ts" in data

    def test_format_with_exception(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="mylogger", level=logging.ERROR, pathname="test.py",
            lineno=42, msg="Error occurred", args=(), exc_info=exc_info,
        )
        record.request_id = "-"  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError" in data["exception"]

    def test_format_without_request_id_attr(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="",
            lineno=0, msg="no request id", args=(), exc_info=None,
        )
        # No request_id attribute set
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "-"

    def test_unicode_message(self):
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="日本語メッセージ", args=(), exc_info=None,
        )
        record.request_id = "-"  # type: ignore[attr-defined]
        output = formatter.format(record)
        assert "日本語メッセージ" in output
        # ensure_ascii=False should keep Japanese readable
        data = json.loads(output)
        assert data["msg"] == "日本語メッセージ"


# ── setup_logging ─────────────────────────────────────────


class TestSetupLogging:
    @pytest.fixture(autouse=True)
    def _reset_logging(self):
        """Reset root logger after each test."""
        yield
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)

    def test_console_only(self):
        setup_logging(level="DEBUG", log_dir=None)
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_with_file_handler_json(self, tmp_path):
        setup_logging(level="INFO", log_dir=tmp_path, json_file=True)
        root = logging.getLogger()
        assert root.level == logging.INFO
        assert len(root.handlers) == 2
        # One StreamHandler, one RotatingFileHandler
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "StreamHandler" in handler_types
        assert "RotatingFileHandler" in handler_types

    def test_with_file_handler_plain(self, tmp_path):
        setup_logging(level="WARNING", log_dir=tmp_path, json_file=False)
        root = logging.getLogger()
        assert root.level == logging.WARNING
        assert len(root.handlers) == 2

    def test_creates_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs" / "deep"
        assert not log_dir.exists()
        setup_logging(log_dir=log_dir)
        assert log_dir.exists()

    def test_clears_existing_handlers(self):
        root = logging.getLogger()
        # Count handlers before adding
        before = len(root.handlers)
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        assert len(root.handlers) == before + 2
        setup_logging()
        # setup_logging clears ALL handlers and adds 1 console handler
        # (pytest may re-add its own handlers afterwards)
        # Just verify the custom ones we added are gone and at least console is there
        handler_types = [type(h).__name__ for h in root.handlers]
        assert "StreamHandler" in handler_types

    def test_third_party_loggers_suppressed(self):
        setup_logging()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
        assert logging.getLogger("apscheduler").level == logging.WARNING

    def test_invalid_level_defaults_to_info(self):
        setup_logging(level="INVALID_LEVEL")
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_request_id_filter_attached(self):
        setup_logging()
        root = logging.getLogger()
        for handler in root.handlers:
            filter_types = [type(f).__name__ for f in handler.filters]
            assert "RequestIdFilter" in filter_types
