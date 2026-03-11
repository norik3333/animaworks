"""Tests for core.tooling.guide — dynamic tool guide generation."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import patch

from core.tooling.guide import (
    build_tools_guide,
    filter_gated_from_guide,
    load_tool_schemas,
)

# ── build_tools_guide ─────────────────────────────────────────


class TestBuildToolsGuide:
    def test_empty_returns_empty_string(self):
        result = build_tools_guide([], None)
        assert result == ""

    def test_empty_registry_and_no_personal_tools(self):
        result = build_tools_guide([], {})
        assert result == ""

    def test_with_registry_returns_empty(self):
        """build_tools_guide is deprecated and always returns empty."""
        result = build_tools_guide(["web_search"])
        assert result == ""

    def test_with_personal_tools_returns_empty(self):
        """build_tools_guide is deprecated and always returns empty."""
        result = build_tools_guide([], {"my_tool": "/path/to/my_tool.py"})
        assert result == ""


# ── load_tool_schemas ─────────────────────────────────────────


class TestLoadToolSchemas:
    @patch("core.tooling.schemas.load_external_schemas")
    def test_empty_registry_no_personal(self, mock_ext):
        mock_ext.return_value = []
        result = load_tool_schemas([], None)
        assert result == []

    @patch("core.tooling.schemas.load_external_schemas")
    def test_delegates_to_load_external_schemas(self, mock_ext):
        mock_ext.return_value = [{"name": "web_search", "description": "d", "parameters": {}}]
        result = load_tool_schemas(["web_search"])
        mock_ext.assert_called_once_with(["web_search"])
        assert len(result) == 1

    @patch("core.tooling.schemas.load_personal_tool_schemas")
    @patch("core.tooling.schemas.load_external_schemas")
    def test_includes_personal_tool_schemas(self, mock_ext, mock_personal):
        mock_ext.return_value = []
        mock_personal.return_value = [
            {
                "name": "my_tool",
                "description": "My personal tool",
                "parameters": {"type": "object", "properties": {}},
            }
        ]

        result = load_tool_schemas([], {"my_tool": "/path/to/tool.py"})
        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert result[0]["parameters"] == {"type": "object", "properties": {}}

    @patch("core.tooling.schemas.load_personal_tool_schemas")
    @patch("core.tooling.schemas.load_external_schemas")
    def test_personal_tool_without_get_tool_schemas(self, mock_ext, mock_personal):
        mock_ext.return_value = []
        mock_personal.return_value = []

        result = load_tool_schemas([], {"my_tool": "/path/to/tool.py"})
        assert result == []

    @patch("core.tooling.schemas.load_personal_tool_schemas")
    @patch("core.tooling.schemas.load_external_schemas")
    def test_personal_tool_import_error(self, mock_ext, mock_personal):
        mock_ext.return_value = []
        mock_personal.return_value = []

        result = load_tool_schemas([], {"my_tool": "/path/to/tool.py"})
        assert result == []

    @patch("core.tooling.schemas.load_personal_tool_schemas")
    @patch("core.tooling.schemas.load_external_schemas")
    def test_personal_tool_uses_parameters_fallback(self, mock_ext, mock_personal):
        mock_ext.return_value = []
        mock_personal.return_value = [
            {
                "name": "my_tool",
                "description": "Tool",
                "parameters": {"type": "object"},
            }
        ]

        result = load_tool_schemas([], {"my_tool": "/path/to/tool.py"})
        assert result[0]["parameters"] == {"type": "object"}


# ── filter_gated_from_guide ─────────────────────────────────────


class TestFilterGatedFromGuide:
    """Tests for gated action filtering in tool guides."""

    def test_gated_action_lines_removed_when_not_permitted(self):
        """Gated action CLI lines are removed when action is not in permitted set."""
        guide = """### Gmail
```bash
animaworks-tool gmail unread -n 10
animaworks-tool gmail send --to "x" --subject "s" --body "b"
animaworks-tool gmail draft --to "x" --subject "s" --body "b"
```"""
        permitted = {"gmail"}
        result = filter_gated_from_guide(guide, "gmail", permitted)
        assert "animaworks-tool gmail send" not in result
        assert "animaworks-tool gmail unread" in result
        assert "animaworks-tool gmail draft" in result

    def test_gated_action_lines_kept_when_permitted(self):
        """Gated action CLI lines are kept when action is explicitly permitted."""
        guide = """### Gmail
```bash
animaworks-tool gmail unread -n 10
animaworks-tool gmail send --to "x" --subject "s" --body "b"
```"""
        permitted = {"gmail", "gmail_send"}
        result = filter_gated_from_guide(guide, "gmail", permitted)
        assert "animaworks-tool gmail send" in result
        assert "animaworks-tool gmail unread" in result

    def test_non_gated_action_lines_always_kept(self):
        """Non-gated action lines are always kept regardless of permitted set."""
        guide = """### Gmail
```bash
animaworks-tool gmail unread -n 10
animaworks-tool gmail draft --to "x" --subject "s" --body "b"
```"""
        permitted = {"gmail"}
        result = filter_gated_from_guide(guide, "gmail", permitted)
        assert "animaworks-tool gmail unread" in result
        assert "animaworks-tool gmail draft" in result

    def test_tool_without_gated_actions_unchanged(self):
        """Tools with no gated actions return guide unchanged."""
        guide = """### web_search
```bash
animaworks-tool web_search search "query"
```"""
        permitted = {"web_search"}
        result = filter_gated_from_guide(guide, "web_search", permitted)
        assert result == guide

    def test_unknown_tool_unchanged(self):
        """Unknown tool names return guide unchanged."""
        guide = "animaworks-tool fake_tool do_something"
        permitted = set()
        result = filter_gated_from_guide(guide, "nonexistent_tool", permitted)
        assert result == guide
