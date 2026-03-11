"""Tests for gated action checks in ToolHandler._handle_use_tool."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tooling.handler import ToolHandler

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-anima"
    d.mkdir(parents=True)
    (d / "permissions.md").write_text("", encoding="utf-8")
    return d


@pytest.fixture
def memory(anima_dir: Path) -> MagicMock:
    m = MagicMock()
    m.read_permissions.return_value = ""
    m.search_memory_text.return_value = []
    return m


@pytest.fixture
def handler_with_gmail(anima_dir: Path, memory: MagicMock) -> ToolHandler:
    """Handler with gmail in registry (gmail_send is gated)."""
    return ToolHandler(
        anima_dir=anima_dir,
        memory=memory,
        messenger=None,
        tool_registry=["gmail"],
    )


# ── Gated action blocked ──────────────────────────────────────


class TestGatedActionBlocked:
    """Gated actions without explicit permission are blocked."""

    def test_gmail_send_blocked_without_permission(self, handler_with_gmail: ToolHandler, memory: MagicMock) -> None:
        """gmail_send is gated; without gmail_send: yes, should be denied."""
        memory.read_permissions.return_value = "## 外部ツール\n- gmail: yes\n"

        result = handler_with_gmail.handle(
            "use_tool",
            {
                "tool_name": "gmail",
                "action": "send",
                "args": {
                    "to": "test@example.com",
                    "subject": "Test",
                    "body": "Body",
                },
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed.get("error_type") == "PermissionDenied"
        assert "gmail_send" in parsed.get("message", "") or "send" in parsed.get("message", "")
        assert "permissions.md" in parsed.get("message", "")

    def test_gated_action_blocked_with_all_yes_but_no_action_permit(
        self, handler_with_gmail: ToolHandler, memory: MagicMock
    ) -> None:
        """all: yes does not auto-allow gated actions."""
        memory.read_permissions.return_value = "## 外部ツール\n- all: yes\n"

        result = handler_with_gmail.handle(
            "use_tool",
            {
                "tool_name": "gmail",
                "action": "send",
                "args": {"to": "x@y.z", "subject": "S", "body": "B"},
            },
        )
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed.get("error_type") == "PermissionDenied"


# ── Gated action allowed ──────────────────────────────────────


class TestGatedActionAllowed:
    """Gated actions with explicit permission are allowed."""

    def test_gmail_send_allowed_with_explicit_permit(self, handler_with_gmail: ToolHandler, memory: MagicMock) -> None:
        """gmail_send: yes explicitly permits the gated action."""
        memory.read_permissions.return_value = "## 外部ツール\n- gmail: yes\n- gmail_send: yes\n"

        with patch("core.tooling.handler.ExternalToolDispatcher._call_module") as call_mod:
            call_mod.return_value = '{"success": true}'

            result = handler_with_gmail.handle(
                "use_tool",
                {
                    "tool_name": "gmail",
                    "action": "send",
                    "args": {
                        "to": "test@example.com",
                        "subject": "Test",
                        "body": "Body",
                    },
                },
            )

            call_mod.assert_called_once()
            assert "success" in result or "true" in result

    def test_non_gated_action_allowed_with_tool_permit(
        self, handler_with_gmail: ToolHandler, memory: MagicMock
    ) -> None:
        """gmail_unread is not gated; gmail: yes is sufficient."""
        memory.read_permissions.return_value = "## 外部ツール\n- gmail: yes\n"

        with patch("core.tooling.handler.ExternalToolDispatcher._call_module") as call_mod:
            call_mod.return_value = "[]"

            result = handler_with_gmail.handle(
                "use_tool",
                {
                    "tool_name": "gmail",
                    "action": "unread",
                    "args": {},
                },
            )

            call_mod.assert_called_once()
            assert result == "[]"
