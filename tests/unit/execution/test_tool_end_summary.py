# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for tool_end chunk summary extraction in _agent_cycle.py.

Verifies that the completed_tools list built during streaming correctly
uses record.result_summary when available (LiteLLM path) and falls back
to tool_name when record is absent (Agent SDK path).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from core.execution.base import ToolCallRecord


def _extract_summary(chunk: dict[str, Any]) -> str:
    """Replicate the summary extraction logic from _agent_cycle.py tool_end handler."""
    record = chunk.get("record")
    return (
        (record.result_summary if record else "")
        or chunk.get("tool_name", "unknown")
    )


# ── LiteLLM path: record with result_summary ────────────────────


class TestToolEndSummaryWithRecord:
    """LiteLLM path provides a ToolCallRecord in the tool_end chunk."""

    def test_uses_result_summary_from_record(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "web_search",
            "tool_id": "call_123",
            "record": ToolCallRecord(
                tool_name="web_search",
                tool_id="call_123",
                result_summary="Found 5 results about Python async",
            ),
        }
        assert _extract_summary(chunk) == "Found 5 results about Python async"

    def test_falls_back_to_tool_name_when_result_summary_empty(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "web_search",
            "tool_id": "call_456",
            "record": ToolCallRecord(
                tool_name="web_search",
                tool_id="call_456",
                result_summary="",
            ),
        }
        assert _extract_summary(chunk) == "web_search"

    def test_preserves_long_result_summary(self) -> None:
        long_summary = "x" * 500
        chunk = {
            "type": "tool_end",
            "tool_name": "Bash",
            "tool_id": "call_789",
            "record": ToolCallRecord(
                tool_name="Bash",
                tool_id="call_789",
                result_summary=long_summary,
            ),
        }
        assert _extract_summary(chunk) == long_summary


# ── Agent SDK path: no record ────────────────────────────────────


class TestToolEndSummaryWithoutRecord:
    """Agent SDK path does not include a record in tool_end chunks."""

    def test_falls_back_to_tool_name(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "Read",
            "tool_id": "call_abc",
        }
        assert _extract_summary(chunk) == "Read"

    def test_falls_back_to_unknown_when_no_tool_name(self) -> None:
        chunk: dict[str, Any] = {
            "type": "tool_end",
        }
        assert _extract_summary(chunk) == "unknown"

    def test_record_none_explicitly(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "Bash",
            "tool_id": "call_def",
            "record": None,
        }
        assert _extract_summary(chunk) == "Bash"


# ── completed_tools list construction ─────────────────────────────


class TestCompletedToolsConstruction:
    """Verify the full completed_tools dict structure matches expectations."""

    def _build_completed_tool(self, chunk: dict[str, Any]) -> dict[str, str]:
        record = chunk.get("record")
        summary = (
            (record.result_summary if record else "")
            or chunk.get("tool_name", "unknown")
        )
        return {
            "tool_name": chunk.get("tool_name", ""),
            "tool_id": chunk.get("tool_id", ""),
            "summary": summary,
        }

    def test_litellm_tool_end_has_result_summary(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "web_search",
            "tool_id": "tc_001",
            "record": ToolCallRecord(
                tool_name="web_search",
                tool_id="tc_001",
                result_summary="3 results found for 'Python async patterns'",
            ),
        }
        entry = self._build_completed_tool(chunk)
        assert entry == {
            "tool_name": "web_search",
            "tool_id": "tc_001",
            "summary": "3 results found for 'Python async patterns'",
        }

    def test_agent_sdk_tool_end_uses_tool_name_as_summary(self) -> None:
        chunk = {
            "type": "tool_end",
            "tool_name": "Bash",
            "tool_id": "tc_002",
        }
        entry = self._build_completed_tool(chunk)
        assert entry == {
            "tool_name": "Bash",
            "tool_id": "tc_002",
            "summary": "Bash",
        }

    def test_no_longer_produces_redundant_name_name(self) -> None:
        """Before the fix, retry prompts would show 'web_search: web_search'.
        After the fix with a record, it shows 'web_search: <actual summary>'.
        """
        chunk = {
            "type": "tool_end",
            "tool_name": "web_search",
            "tool_id": "tc_003",
            "record": ToolCallRecord(
                tool_name="web_search",
                tool_id="tc_003",
                result_summary="Found documentation for asyncio.Lock",
            ),
        }
        entry = self._build_completed_tool(chunk)
        assert entry["tool_name"] != entry["summary"]
        assert entry["summary"] == "Found documentation for asyncio.Lock"


# ── E2E: build_stream_retry_prompt integration ──────────────────


class TestRetryPromptWithRealSummary:
    """Verify that the retry prompt reads better with real summaries."""

    def test_retry_prompt_contains_result_summary(self) -> None:
        from core.memory.shortterm import StreamCheckpoint
        from core.execution._session import build_stream_retry_prompt

        cp = StreamCheckpoint(
            original_prompt="Search for Python best practices",
            completed_tools=[
                {
                    "tool_name": "web_search",
                    "summary": "Found 10 results about Python best practices",
                },
                {
                    "tool_name": "Read",
                    "summary": "Read README.md (245 lines)",
                },
            ],
            accumulated_text="Analyzing search results...",
        )
        prompt = build_stream_retry_prompt(cp)

        assert "Found 10 results about Python best practices" in prompt
        assert "Read README.md (245 lines)" in prompt
        assert "web_search: web_search" not in prompt

    def test_retry_prompt_with_fallback_summary(self) -> None:
        from core.memory.shortterm import StreamCheckpoint
        from core.execution._session import build_stream_retry_prompt

        cp = StreamCheckpoint(
            original_prompt="Deploy application",
            completed_tools=[
                {
                    "tool_name": "Bash",
                    "summary": "Bash",
                },
            ],
            accumulated_text="",
        )
        prompt = build_stream_retry_prompt(cp)

        assert "Bash" in prompt
