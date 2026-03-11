"""Tests for gated action checks in ExternalToolDispatcher.dispatch."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.tooling.dispatch import ExternalToolDispatcher

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-anima"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def dispatcher() -> ExternalToolDispatcher:
    return ExternalToolDispatcher(tool_registry=["gmail"], personal_tools={})


# ── Gated action blocked ──────────────────────────────────────


class TestDispatchGatedBlocked:
    """Dispatch blocks gated actions when not permitted."""

    def test_gmail_send_blocked(self, dispatcher: ExternalToolDispatcher, anima_dir: Path) -> None:
        """gmail_send without gmail_send: yes returns error."""
        (anima_dir / "permissions.md").write_text(
            "## 外部ツール\n- gmail: yes\n",
            encoding="utf-8",
        )

        result = dispatcher.dispatch(
            "gmail_send",
            {
                "anima_dir": str(anima_dir),
                "to": "x@y.z",
                "subject": "S",
                "body": "B",
            },
        )

        assert result is not None
        parsed = json.loads(result)
        assert parsed.get("status") == "error"
        assert parsed.get("error_type") == "PermissionDenied"
        assert "gmail_send" in parsed.get("message", "") or "send" in parsed.get("message", "")


# ── Gated action allowed ──────────────────────────────────────


class TestDispatchGatedAllowed:
    """Dispatch allows gated actions when permitted."""

    def test_gmail_send_allowed_with_explicit_permit(self, dispatcher: ExternalToolDispatcher, anima_dir: Path) -> None:
        """gmail_send: yes permits the action; dispatch proceeds to module."""
        (anima_dir / "permissions.md").write_text(
            "## 外部ツール\n- gmail: yes\n- gmail_send: yes\n",
            encoding="utf-8",
        )

        with patch.object(dispatcher, "_dispatch_from_registry", return_value='{"success": true}') as mock_reg:
            result = dispatcher.dispatch(
                "gmail_send",
                {
                    "anima_dir": str(anima_dir),
                    "to": "x@y.z",
                    "subject": "S",
                    "body": "B",
                },
            )

            mock_reg.assert_called_once()
            assert result == '{"success": true}'

    def test_missing_anima_dir_skips_gated_check(self, dispatcher: ExternalToolDispatcher) -> None:
        """When anima_dir is missing, gated check is skipped; dispatch proceeds."""
        with patch.object(dispatcher, "_dispatch_from_registry", return_value='{"success": true}') as mock_reg:
            result = dispatcher.dispatch(
                "gmail_send",
                {"to": "x@y.z", "subject": "S", "body": "B"},
            )

            mock_reg.assert_called_once()
            assert result == '{"success": true}'
