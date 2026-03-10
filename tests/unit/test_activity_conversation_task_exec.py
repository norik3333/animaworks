"""Unit tests for task_exec_start/task_exec_end in conversation view API."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.activity import ActivityEntry, ActivityLogger


# ── Helpers ───────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory with activity_log."""
    d = tmp_path / "animas" / "test-anima"
    (d / "activity_log").mkdir(parents=True)
    return d


@pytest.fixture
def activity_logger(anima_dir: Path) -> ActivityLogger:
    return ActivityLogger(anima_dir)


def _make_entry(
    type: str,
    ts: str,
    *,
    content: str = "",
    summary: str = "",
    **kwargs: object,
) -> ActivityEntry:
    return ActivityEntry(ts=ts, type=type, content=content, summary=summary, **kwargs)


# ── _CONVERSATION_TYPES ───────────────────────────────────


class TestConversationTypes:
    """task_exec_start and task_exec_end are in _CONVERSATION_TYPES."""

    def test_task_exec_start_in_conversation_types(self) -> None:
        assert "task_exec_start" in ActivityLogger._CONVERSATION_TYPES

    def test_task_exec_end_in_conversation_types(self) -> None:
        assert "task_exec_end" in ActivityLogger._CONVERSATION_TYPES


# ── _entries_to_messages ──────────────────────────────────


class TestEntriesToMessages:
    """_entries_to_messages correctly converts task_exec entries to system messages."""

    def test_task_exec_start_becomes_system_message(
        self, activity_logger: ActivityLogger
    ) -> None:
        """task_exec_start entry -> system message with _trigger: task."""
        entries = [
            _make_entry("task_exec_start", "2026-03-10T09:00:00+09:00"),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "system"
        assert msg["_trigger"] == "task"
        assert msg["from_person"] == ""
        assert msg["tool_calls"] == []
        assert "タスク実行開始" in msg["content"] or "Task execution started" in msg["content"]

    def test_task_exec_start_uses_summary_when_present(
        self, activity_logger: ActivityLogger
    ) -> None:
        """task_exec_start with summary uses summary as content."""
        entries = [
            _make_entry(
                "task_exec_start",
                "2026-03-10T09:00:00+09:00",
                summary="pending/task_abc.json を実行",
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 1
        assert messages[0]["content"] == "pending/task_abc.json を実行"

    def test_task_exec_end_becomes_system_message(
        self, activity_logger: ActivityLogger
    ) -> None:
        """task_exec_end entry -> system message with _trigger: task."""
        entries = [
            _make_entry("task_exec_end", "2026-03-10T09:05:00+09:00"),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "system"
        assert msg["_trigger"] == "task"
        assert msg["from_person"] == ""
        assert msg["tool_calls"] == []
        assert "タスク実行完了" in msg["content"] or "Task execution completed" in msg["content"]

    def test_task_exec_end_prefers_summary_then_content(
        self, activity_logger: ActivityLogger
    ) -> None:
        """task_exec_end uses summary > content > i18n label."""
        entries = [
            _make_entry(
                "task_exec_end",
                "2026-03-10T09:05:00+09:00",
                summary="タスク完了: レポート作成",
                content="Full output...",
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert messages[0]["content"] == "タスク完了: レポート作成"

        entries2 = [
            _make_entry(
                "task_exec_end",
                "2026-03-10T09:05:00+09:00",
                content="Fallback content",
            ),
        ]
        messages2 = activity_logger._entries_to_messages(entries2)
        assert messages2[0]["content"] == "Fallback content"

    def test_task_exec_start_end_sequence(
        self, activity_logger: ActivityLogger
    ) -> None:
        """task_exec_start -> tool_use -> task_exec_end produces correct messages."""
        entries = [
            _make_entry("task_exec_start", "2026-03-10T09:00:00+09:00"),
            _make_entry(
                "tool_use",
                "2026-03-10T09:01:00+09:00",
                tool="read_memory_file",
                meta={"tool_use_id": "tu_1", "args": {"path": "state/current_task.md"}},
            ),
            _make_entry(
                "tool_result",
                "2026-03-10T09:01:01+09:00",
                content="task content",
                meta={"tool_use_id": "tu_1"},
            ),
            _make_entry(
                "task_exec_end",
                "2026-03-10T09:02:00+09:00",
                summary="完了",
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 2  # task_exec_start (system) + task_exec_end (system)
        assert messages[0]["_trigger"] == "task"
        assert messages[1]["_trigger"] == "task"
        assert messages[1]["content"] == "完了"


# ── _group_into_sessions ──────────────────────────────────


class TestGroupIntoSessions:
    """_group_into_sessions groups task_exec messages with trigger: task."""

    def test_task_exec_messages_grouped_with_trigger_task(self) -> None:
        """Messages with _trigger: task produce session with trigger: task."""
        messages = [
            {
                "ts": "2026-03-10T09:00:00+09:00",
                "role": "system",
                "content": "タスク実行開始",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "task",
            },
            {
                "ts": "2026-03-10T09:02:00+09:00",
                "role": "system",
                "content": "タスク実行完了",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "task",
            },
        ]
        sessions = ActivityLogger._group_into_sessions(messages, gap_minutes=10)
        assert len(sessions) == 1
        assert sessions[0]["trigger"] == "task"
        assert len(sessions[0]["messages"]) == 2
        assert sessions[0]["session_start"] == "2026-03-10T09:00:00+09:00"
        assert sessions[0]["session_end"] == "2026-03-10T09:02:00+09:00"

    def test_orphaned_task_exec_start_only(self) -> None:
        """task_exec_start without end (crash/in-progress) still grouped."""
        messages = [
            {
                "ts": "2026-03-10T09:00:00+09:00",
                "role": "system",
                "content": "タスク実行開始",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "task",
            },
        ]
        sessions = ActivityLogger._group_into_sessions(messages, gap_minutes=10)
        assert len(sessions) == 1
        assert sessions[0]["trigger"] == "task"
        assert len(sessions[0]["messages"]) == 1

    def test_task_exec_session_separated_by_gap(self) -> None:
        """task_exec messages with 15-min gap -> 2 sessions."""
        messages = [
            {
                "ts": "2026-03-10T09:00:00+09:00",
                "role": "system",
                "content": "開始1",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "task",
            },
            {
                "ts": "2026-03-10T09:16:00+09:00",
                "role": "system",
                "content": "開始2",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "task",
            },
        ]
        sessions = ActivityLogger._group_into_sessions(messages, gap_minutes=10)
        assert len(sessions) == 2
        assert sessions[0]["trigger"] == "task"
        assert sessions[1]["trigger"] == "task"

    def test_trigger_change_splits_session(self) -> None:
        """Heartbeat followed by chat within 10min -> separate sessions."""
        messages = [
            {
                "ts": "2026-03-10T08:00:00+09:00",
                "role": "system",
                "content": "定期巡回開始",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "heartbeat",
            },
            {
                "ts": "2026-03-10T08:03:00+09:00",
                "role": "system",
                "content": "定期巡回完了",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "heartbeat",
            },
            {
                "ts": "2026-03-10T08:05:00+09:00",
                "role": "human",
                "content": "こんにちは",
                "from_person": "human",
                "tool_calls": [],
            },
            {
                "ts": "2026-03-10T08:06:00+09:00",
                "role": "assistant",
                "content": "はい、お手伝いします",
                "from_person": "",
                "tool_calls": [],
            },
        ]
        sessions = ActivityLogger._group_into_sessions(messages, gap_minutes=10)
        assert len(sessions) == 2
        assert sessions[0]["trigger"] == "heartbeat"
        assert len(sessions[0]["messages"]) == 2
        assert sessions[1]["trigger"] == "chat"
        assert len(sessions[1]["messages"]) == 2
        assert sessions[1]["messages"][0]["role"] == "human"

    def test_chat_then_cron_splits_session(self) -> None:
        """Chat followed by cron within 10min -> separate sessions."""
        messages = [
            {
                "ts": "2026-03-10T08:00:00+09:00",
                "role": "human",
                "content": "テスト",
                "from_person": "human",
                "tool_calls": [],
            },
            {
                "ts": "2026-03-10T08:01:00+09:00",
                "role": "assistant",
                "content": "応答",
                "from_person": "",
                "tool_calls": [],
            },
            {
                "ts": "2026-03-10T08:04:00+09:00",
                "role": "system",
                "content": "Chatworkメンション監視",
                "from_person": "",
                "tool_calls": [],
                "_trigger": "cron",
            },
        ]
        sessions = ActivityLogger._group_into_sessions(messages, gap_minutes=10)
        assert len(sessions) == 2
        assert sessions[0]["trigger"] == "chat"
        assert len(sessions[0]["messages"]) == 2
        assert sessions[1]["trigger"] == "cron"
        assert len(sessions[1]["messages"]) == 1
