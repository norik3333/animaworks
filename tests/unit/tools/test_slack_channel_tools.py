# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for slack_channel_post / slack_channel_update gated actions.

Covers:
- EXECUTION_PROFILE gated flags
- get_tool_schemas() schema presence
- dispatch() routing for channel_post / channel_update
- taskboard_md_to_slack() conversion
- Trust level registration in _sanitize.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ── EXECUTION_PROFILE ───────────────────────────────────────


class TestExecutionProfile:
    """Gated flags in EXECUTION_PROFILE."""

    def test_channel_post_is_gated(self):
        from core.tools.slack import EXECUTION_PROFILE

        assert EXECUTION_PROFILE["channel_post"]["gated"] is True

    def test_channel_update_is_gated(self):
        from core.tools.slack import EXECUTION_PROFILE

        assert EXECUTION_PROFILE["channel_update"]["gated"] is True

    def test_channel_post_not_background_eligible(self):
        from core.tools.slack import EXECUTION_PROFILE

        assert EXECUTION_PROFILE["channel_post"]["background_eligible"] is False

    def test_channel_update_not_background_eligible(self):
        from core.tools.slack import EXECUTION_PROFILE

        assert EXECUTION_PROFILE["channel_update"]["background_eligible"] is False


# ── get_tool_schemas ────────────────────────────────────────


class TestToolSchemas:
    """Schema definitions returned by get_tool_schemas()."""

    def test_returns_two_schemas(self):
        from core.tools.slack import get_tool_schemas

        schemas = get_tool_schemas()
        assert len(schemas) == 2

    def test_schema_names(self):
        from core.tools.slack import get_tool_schemas

        names = {s["name"] for s in get_tool_schemas()}
        assert names == {"slack_channel_post", "slack_channel_update"}

    def test_channel_post_required_fields(self):
        from core.tools.slack import get_tool_schemas

        schema = next(s for s in get_tool_schemas() if s["name"] == "slack_channel_post")
        required = schema["input_schema"]["required"]
        assert "channel_id" in required
        assert "text" in required

    def test_channel_update_required_fields(self):
        from core.tools.slack import get_tool_schemas

        schema = next(s for s in get_tool_schemas() if s["name"] == "slack_channel_update")
        required = schema["input_schema"]["required"]
        assert "channel_id" in required
        assert "ts" in required
        assert "text" in required


# ── dispatch ────────────────────────────────────────────────


class TestDispatchChannelPost:
    """dispatch('slack_channel_post', ...) routing."""

    @patch("core.tools.slack._resolve_slack_identity", return_value=("sakura", ""))
    @patch("core.tools.slack._resolve_slack_token", return_value="xoxb-test")
    @patch("core.tools.slack.SlackClient")
    def test_posts_message_and_returns_ts(self, mock_cls, mock_token, mock_identity):
        from core.tools.slack import dispatch

        mock_client = MagicMock()
        mock_client.post_message.return_value = {"ok": True, "ts": "1234567890.123456"}
        mock_cls.return_value = mock_client

        result = dispatch(
            "slack_channel_post",
            {
                "channel_id": "C123ABC",
                "text": "Hello **world**",
            },
        )

        assert result["status"] == "ok"
        assert result["ts"] == "1234567890.123456"
        assert result["channel"] == "C123ABC"
        mock_client.post_message.assert_called_once()
        call_kwargs = mock_client.post_message.call_args
        assert call_kwargs[0][0] == "C123ABC"

    @patch("core.tools.slack._resolve_slack_identity", return_value=("mei", "https://cdn/mei.png"))
    @patch("core.tools.slack._resolve_slack_token", return_value="xoxb-test")
    @patch("core.tools.slack.SlackClient")
    def test_passes_identity(self, mock_cls, mock_token, mock_identity):
        from core.tools.slack import dispatch

        mock_client = MagicMock()
        mock_client.post_message.return_value = {"ok": True, "ts": "123"}
        mock_cls.return_value = mock_client

        dispatch("slack_channel_post", {"channel_id": "C1", "text": "hi"})

        _, kwargs = mock_client.post_message.call_args
        assert kwargs["username"] == "mei"
        assert kwargs["icon_url"] == "https://cdn/mei.png"


class TestDispatchChannelUpdate:
    """dispatch('slack_channel_update', ...) routing."""

    @patch("core.tools.slack._resolve_slack_token", return_value="xoxb-test")
    @patch("core.tools.slack.SlackClient")
    def test_updates_message(self, mock_cls, mock_token):
        from core.tools.slack import dispatch

        mock_client = MagicMock()
        mock_client.update_message.return_value = {"ok": True}
        mock_cls.return_value = mock_client

        result = dispatch(
            "slack_channel_update",
            {
                "channel_id": "C123ABC",
                "ts": "1234567890.123456",
                "text": "Updated text",
            },
        )

        assert result["status"] == "ok"
        assert result["ts"] == "1234567890.123456"
        mock_client.update_message.assert_called_once_with(
            "C123ABC",
            "1234567890.123456",
            "Updated text",
        )


# ── taskboard_md_to_slack ──────────────────────────────────


class TestTaskboardMdToSlack:
    """Markdown task-board → Slack mrkdwn conversion."""

    def test_converts_table_rows_to_bullets(self):
        from core.tools.slack import taskboard_md_to_slack

        md = """\
## 🟡 進行中
| # | タスク | 担当 | 状態 | 期限 |
|---|--------|------|------|------|
| B1 | API修正 | sakura | 着手 | 3/10 |
"""
        result = taskboard_md_to_slack(md)
        assert "• B1: API修正（sakura）" in result

    def test_strips_completed_section(self):
        from core.tools.slack import taskboard_md_to_slack

        md = """\
## 🟡 進行中
| # | タスク | 担当 | 状態 | 期限 |
|---|--------|------|------|------|
| T1 | Fix bug | mei | WIP | 3/10 |

## ✅ 今週完了
| タスク | 担当 | 完了日 |
|--------|------|--------|
| Old task | rin | 3/5 |
"""
        result = taskboard_md_to_slack(md)
        assert "Old task" not in result
        assert "Fix bug" in result

    def test_adds_footer(self):
        from core.tools.slack import taskboard_md_to_slack

        result = taskboard_md_to_slack("## Title\nSome text")
        assert "shared/task-board.md" in result

    def test_section_headers_bold(self):
        from core.tools.slack import taskboard_md_to_slack

        result = taskboard_md_to_slack("## 🔴 ブロック中\nNothing here")
        assert "*🔴 ブロック中*" in result

    def test_skips_table_separator(self):
        from core.tools.slack import taskboard_md_to_slack

        md = """\
| # | タスク | 担当 |
|---|--------|------|
| 1 | Test | mei |
"""
        result = taskboard_md_to_slack(md)
        assert "---" not in result


# ── SlackClient methods ────────────────────────────────────


class TestSlackClientUpdateMessage:
    """SlackClient.update_message() method."""

    @patch("core.tools.slack._require_slack_sdk")
    def test_calls_chat_update(self, mock_sdk):
        from core.tools.slack import SlackClient

        client = SlackClient.__new__(SlackClient)
        client._call = MagicMock(return_value={"ok": True})

        client.update_message("C123", "123.456", "new text")
        client._call.assert_called_once_with(
            "chat_update",
            channel="C123",
            ts="123.456",
            text="new text",
        )


class TestSlackClientPinsAdd:
    """SlackClient.pins_add() method."""

    @patch("core.tools.slack._require_slack_sdk")
    def test_calls_pins_add(self, mock_sdk):
        from core.tools.slack import SlackClient

        client = SlackClient.__new__(SlackClient)
        client._call = MagicMock(return_value={"ok": True})

        client.pins_add("C123", "123.456")
        client._call.assert_called_once_with(
            "pins_add",
            channel="C123",
            timestamp="123.456",
        )


# ── Trust level ────────────────────────────────────────────


class TestTrustLevel:
    """Trust level registration in _sanitize.py."""

    def test_channel_post_untrusted(self):
        from core.execution._sanitize import TOOL_TRUST_LEVELS

        assert TOOL_TRUST_LEVELS["slack_channel_post"] == "untrusted"

    def test_channel_update_untrusted(self):
        from core.execution._sanitize import TOOL_TRUST_LEVELS

        assert TOOL_TRUST_LEVELS["slack_channel_update"] == "untrusted"


# ── Gating integration ─────────────────────────────────────


class TestGatingIntegration:
    """Gated action check via permissions infrastructure."""

    def test_channel_post_blocked_without_permission(self):
        from core.tooling.permissions import is_action_gated

        permitted: set[str] = {"slack"}
        assert is_action_gated("slack", "channel_post", permitted) is True

    def test_channel_post_allowed_with_explicit_permission(self):
        from core.tooling.permissions import is_action_gated

        permitted: set[str] = {"slack", "slack_channel_post"}
        assert is_action_gated("slack", "channel_post", permitted) is False

    def test_channel_update_blocked_without_permission(self):
        from core.tooling.permissions import is_action_gated

        permitted: set[str] = {"slack"}
        assert is_action_gated("slack", "channel_update", permitted) is True

    def test_channel_update_allowed_with_explicit_permission(self):
        from core.tooling.permissions import is_action_gated

        permitted: set[str] = {"slack", "slack_channel_update"}
        assert is_action_gated("slack", "channel_update", permitted) is False
