from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.execution._sanitize."""

import pytest

from core.execution._sanitize import (
    TOOL_TRUST_LEVELS,
    wrap_priming,
    wrap_tool_result,
)


# ── wrap_tool_result ──────────────────────────────────────────


def test_wrap_tool_result_trusted() -> None:
    """Known trusted tool wraps with trust="trusted"."""
    result = wrap_tool_result("search_memory", "found 3 matches")
    assert 'trust="trusted"' in result
    assert "found 3 matches" in result


def test_wrap_tool_result_medium() -> None:
    """Known medium tool wraps with trust="medium"."""
    result = wrap_tool_result("read_file", "file contents here")
    assert 'trust="medium"' in result
    assert "file contents here" in result


def test_wrap_tool_result_untrusted() -> None:
    """Known untrusted tool wraps with trust="untrusted"."""
    result = wrap_tool_result("web_search", "search results from web")
    assert 'trust="untrusted"' in result
    assert "search results from web" in result


def test_wrap_tool_result_unknown_tool() -> None:
    """Unknown tool name defaults to trust="untrusted"."""
    result = wrap_tool_result("unknown_tool_xyz", "some output")
    assert 'trust="untrusted"' in result
    assert 'tool="unknown_tool_xyz"' in result


def test_wrap_tool_result_empty_string() -> None:
    """Empty string returns empty string unchanged."""
    result = wrap_tool_result("search_memory", "")
    assert result == ""


def test_wrap_tool_result_none_returns_none() -> None:
    """None input returns None (falsy check)."""
    result = wrap_tool_result("search_memory", None)  # type: ignore[arg-type]
    assert result is None


def test_wrap_tool_result_contains_content() -> None:
    """Result string is inside the tags."""
    content = "internal data from memory"
    result = wrap_tool_result("read_memory_file", content)
    assert content in result
    assert "<tool_result" in result
    assert "</tool_result>" in result


def test_wrap_tool_result_multiline_content() -> None:
    """Multiline content is wrapped correctly."""
    content = "line1\nline2\nline3"
    result = wrap_tool_result("write_file", content)
    assert "line1\nline2\nline3" in result
    assert 'tool="write_file"' in result
    assert 'trust="medium"' in result


def test_wrap_tool_result_format() -> None:
    """Verify exact format with newlines."""
    result = wrap_tool_result("search_memory", "x")
    expected = '<tool_result tool="search_memory" trust="trusted">\nx\n</tool_result>'
    assert result == expected


# ── wrap_priming ───────────────────────────────────────────────


def test_wrap_priming_default_trust() -> None:
    """Default trust is "mixed"."""
    result = wrap_priming("sender_profile", "user info")
    assert 'trust="mixed"' in result
    assert 'source="sender_profile"' in result


def test_wrap_priming_custom_trust() -> None:
    """Custom trust level is used."""
    result = wrap_priming("recent_activity", "activity log", trust="untrusted")
    assert 'trust="untrusted"' in result
    assert 'source="recent_activity"' in result


def test_wrap_priming_empty_string() -> None:
    """Empty string returns empty string."""
    result = wrap_priming("sender_profile", "")
    assert result == ""


def test_wrap_priming_none_returns_none() -> None:
    """None returns None."""
    result = wrap_priming("sender_profile", None)  # type: ignore[arg-type]
    assert result is None


def test_wrap_priming_format() -> None:
    """Verify exact format."""
    result = wrap_priming("related_knowledge", "knowledge", trust="medium")
    expected = '<priming source="related_knowledge" trust="medium">\nknowledge\n</priming>'
    assert result == expected


# ── TOOL_TRUST_LEVELS ──────────────────────────────────────────


def test_trust_levels_cover_all_high_risk_tools() -> None:
    """All high risk tools (read_channel, web_search, slack_messages, etc.) are "untrusted"."""
    high_risk = [
        "read_channel",
        "read_dm_history",
        "web_search",
        "x_search",
        "x_user_tweets",
        "slack_messages",
        "slack_search",
        "slack_unreplied",
        "slack_channels",
        "chatwork_messages",
        "chatwork_search",
        "chatwork_unreplied",
        "chatwork_mentions",
        "chatwork_rooms",
        "gmail_unread",
        "gmail_read_body",
        "local_llm",
    ]
    for tool in high_risk:
        assert TOOL_TRUST_LEVELS.get(tool) == "untrusted", f"{tool} should be untrusted"


def test_trust_levels_medium_tools() -> None:
    """File tools are "medium"."""
    medium_tools = [
        "read_file",
        "search_code",
        "write_file",
        "edit_file",
        "execute_command",
    ]
    for tool in medium_tools:
        assert TOOL_TRUST_LEVELS.get(tool) == "medium", f"{tool} should be medium"


def test_trust_levels_trusted_tools() -> None:
    """Memory tools are "trusted"."""
    trusted_tools = [
        "search_memory",
        "read_memory_file",
        "write_memory_file",
        "archive_memory_file",
        "skill",
        "list_directory",
        "add_task",
        "update_task",
        "list_tasks",
        "post_channel",
        "send_message",
    ]
    for tool in trusted_tools:
        assert TOOL_TRUST_LEVELS.get(tool) == "trusted", f"{tool} should be trusted"
