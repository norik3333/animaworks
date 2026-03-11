"""Unit tests for thinking_text handling in SSE done events."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json


from server.routes.chat import _handle_chunk, _chunk_to_event


class TestDoneEventThinkingText:
    """Verify that thinking_text is stripped from done SSE and replaced with thinking_summary."""

    def _make_cycle_done_chunk(self, thinking_text: str = "", summary: str = "response"):
        return {
            "type": "cycle_done",
            "cycle_result": {
                "trigger": "chat",
                "action": "responded",
                "summary": summary,
                "thinking_text": thinking_text,
                "duration_ms": 100,
                "context_usage_ratio": 0.5,
                "session_chained": False,
                "total_turns": 1,
                "tool_call_records": [{"name": "test_tool"}],
                "usage": None,
            },
        }

    def test_thinking_text_removed_from_handle_chunk(self):
        chunk = self._make_cycle_done_chunk(thinking_text="secret thinking")
        sse_str, _ = _handle_chunk(chunk)
        assert sse_str is not None
        data_line = [l for l in sse_str.split("\n") if l.startswith("data:")][0]
        data = json.loads(data_line[len("data:"):])
        assert "thinking_text" not in data
        assert data.get("thinking_summary") == "secret thinking"

    def test_thinking_summary_truncated_to_500(self):
        long_thinking = "x" * 1000
        chunk = self._make_cycle_done_chunk(thinking_text=long_thinking)
        sse_str, _ = _handle_chunk(chunk)
        data_line = [l for l in sse_str.split("\n") if l.startswith("data:")][0]
        data = json.loads(data_line[len("data:"):])
        assert len(data["thinking_summary"]) == 500

    def test_empty_thinking_text_gives_null_summary(self):
        chunk = self._make_cycle_done_chunk(thinking_text="")
        sse_str, _ = _handle_chunk(chunk)
        data_line = [l for l in sse_str.split("\n") if l.startswith("data:")][0]
        data = json.loads(data_line[len("data:"):])
        assert data["thinking_summary"] is None

    def test_tool_call_records_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="think")
        sse_str, _ = _handle_chunk(chunk)
        data_line = [l for l in sse_str.split("\n") if l.startswith("data:")][0]
        data = json.loads(data_line[len("data:"):])
        assert "tool_call_records" not in data

    def test_chunk_to_event_thinking_text_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="secret")
        result = _chunk_to_event(chunk)
        assert result is not None
        event_name, payload = result
        assert event_name == "done"
        assert "thinking_text" not in payload
        assert payload.get("thinking_summary") == "secret"

    def test_chunk_to_event_tool_records_removed(self):
        chunk = self._make_cycle_done_chunk(thinking_text="")
        result = _chunk_to_event(chunk)
        assert result is not None
        _, payload = result
        assert "tool_call_records" not in payload
