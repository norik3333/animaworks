"""Unit tests for crash recovery note writing and unread_count improvement.

Tests:
1. _recover_streaming_journal writes recovery_note.md for heartbeat crashes
2. recovery_note is NOT written for chat/task_exec session types
3. recovery_note content contains crash metadata
4. _handle_heartbeat_failure receives dynamic unread_count
5. i18n template anima.recovery_crash_info exists and formats correctly
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch



# ── i18n template tests ──────────────────────────────────────────


class TestRecoveryCrashInfoTemplate:
    """Test the anima.recovery_crash_info i18n template."""

    def test_template_exists(self):
        from core.i18n import _STRINGS

        assert "anima.recovery_crash_info" in _STRINGS

    def test_template_ja(self):
        from core.i18n import t

        result = t(
            "anima.recovery_crash_info",
            locale="ja",
            ts="2026-03-05T12:00:00+09:00",
            recovered_chars=1500,
            tool_calls=3,
            trigger="heartbeat",
        )
        assert "2026-03-05T12:00:00+09:00" in result
        assert "1500" in result
        assert "3" in result
        assert "heartbeat" in result
        assert "クラッシュ復旧" in result

    def test_template_en(self):
        from core.i18n import t

        result = t(
            "anima.recovery_crash_info",
            locale="en",
            ts="2026-03-05T12:00:00+09:00",
            recovered_chars=0,
            tool_calls=0,
            trigger="unknown",
        )
        assert "Crash recovery" in result
        assert "unknown" in result


# ── _recover_streaming_journal recovery_note tests ───────────────


@dataclass
class _FakeRecovery:
    trigger: str = "heartbeat"
    from_person: str = ""
    session_id: str = ""
    started_at: str = "2026-03-05T11:00:00+09:00"
    recovered_text: str = "partial heartbeat output..."
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    last_event_at: str = "2026-03-05T11:05:00+09:00"
    is_complete: bool = False


class TestRecoverStreamingJournalRecoveryNote:
    """Test that _recover_streaming_journal writes recovery_note.md for heartbeat."""

    def _make_runner(self, tmp_path: Path):
        from core.supervisor.runner import AnimaRunner

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        anima_dir = animas_dir / "test-anima"
        anima_dir.mkdir()
        (anima_dir / "state").mkdir(parents=True)
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()

        runner = AnimaRunner(
            anima_name="test-anima",
            socket_path=tmp_path / "test.sock",
            animas_dir=animas_dir,
            shared_dir=shared_dir,
        )
        runner.anima = MagicMock()
        return runner

    def test_heartbeat_crash_writes_recovery_note(self, tmp_path: Path):
        """Heartbeat journal recovery should create recovery_note.md."""
        runner = self._make_runner(tmp_path)
        recovery = _FakeRecovery(
            trigger="heartbeat",
            recovered_text="partial output" * 10,
            tool_calls=[{"tool": "search_memory"}],
            last_event_at="2026-03-05T11:05:00+09:00",
        )

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                return_value=["default"],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            runner._recover_streaming_journal()

        note_path = tmp_path / "animas" / "test-anima" / "state" / "recovery_note.md"
        assert note_path.exists(), "recovery_note.md should be created for heartbeat crash"

        content = note_path.read_text(encoding="utf-8")
        assert "2026-03-05T11:05:00+09:00" in content
        assert str(len(recovery.recovered_text)) in content
        assert "1" in content  # tool_calls count
        assert "heartbeat" in content

    def test_chat_crash_does_not_write_recovery_note(self, tmp_path: Path):
        """Chat session journal recovery should NOT create recovery_note.md."""
        runner = self._make_runner(tmp_path)
        recovery = _FakeRecovery(trigger="chat")

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                side_effect=lambda _dir, st: ["default"] if st == "chat" else [],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
            patch("core.memory.conversation.ConversationMemory"),
        ):
            runner._recover_streaming_journal()

        note_path = tmp_path / "animas" / "test-anima" / "state" / "recovery_note.md"
        assert not note_path.exists(), "recovery_note.md should NOT be created for chat crash"

    def test_task_exec_crash_does_not_write_recovery_note(self, tmp_path: Path):
        """task_exec session journal recovery should NOT create recovery_note.md."""
        runner = self._make_runner(tmp_path)
        recovery = _FakeRecovery(trigger="task")

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                side_effect=lambda _dir, st: ["default"] if st == "task_exec" else [],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            runner._recover_streaming_journal()

        note_path = tmp_path / "animas" / "test-anima" / "state" / "recovery_note.md"
        assert not note_path.exists(), "recovery_note.md should NOT be created for task_exec crash"

    def test_recovery_note_uses_fallback_timestamp(self, tmp_path: Path):
        """When last_event_at is empty, should fall back to started_at or now_iso."""
        runner = self._make_runner(tmp_path)
        recovery = _FakeRecovery(
            trigger="heartbeat",
            started_at="2026-03-05T10:00:00+09:00",
            last_event_at="",
            recovered_text="",
            tool_calls=[],
        )

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                return_value=["default"],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            runner._recover_streaming_journal()

        note_path = tmp_path / "animas" / "test-anima" / "state" / "recovery_note.md"
        assert note_path.exists()
        content = note_path.read_text(encoding="utf-8")
        assert "2026-03-05T10:00:00+09:00" in content

    def test_recovery_note_overwrites_existing(self, tmp_path: Path):
        """A new crash should overwrite the existing recovery_note.md."""
        runner = self._make_runner(tmp_path)
        note_path = tmp_path / "animas" / "test-anima" / "state" / "recovery_note.md"
        note_path.write_text("old content", encoding="utf-8")

        recovery = _FakeRecovery(trigger="heartbeat")

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                return_value=["default"],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            runner._recover_streaming_journal()

        content = note_path.read_text(encoding="utf-8")
        assert "old content" not in content
        assert "heartbeat" in content

    def test_recovery_note_write_failure_is_swallowed(self, tmp_path: Path):
        """If writing recovery_note fails, recovery should continue without error."""
        runner = self._make_runner(tmp_path)
        recovery = _FakeRecovery(trigger="heartbeat")

        # Remove state dir to cause write failure
        state_dir = tmp_path / "animas" / "test-anima" / "state"
        state_dir.rmdir()

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                return_value=["default"],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            # Should not raise
            runner._recover_streaming_journal()


# ── unread_count dynamic retrieval tests ─────────────────────────


class TestHeartbeatUnreadCount:
    """Test that _handle_heartbeat_failure receives dynamic unread_count."""

    def test_unread_count_passed_to_failure_handler(self):
        """Source code should call messenger.unread_count() before failure handler."""
        import inspect
        from core._anima_lifecycle import LifecycleMixin

        source = inspect.getsource(LifecycleMixin.run_heartbeat)
        assert "messenger.unread_count()" in source
        assert "await self._handle_heartbeat_failure(exc, [], _unread)" in source

    def test_unread_count_falls_back_to_zero_on_error(self):
        """If messenger.unread_count() raises, should fallback to 0."""
        import inspect
        from core._anima_lifecycle import LifecycleMixin

        source = inspect.getsource(LifecycleMixin.run_heartbeat)
        assert "_unread = 0" in source
        # Verify try/except wraps the count_unread call
        lines = source.split("\n")
        unread_init_idx = next(i for i, l in enumerate(lines) if "_unread = 0" in l)
        try_idx = next(i for i, l in enumerate(lines) if i > unread_init_idx and "try:" in l)
        unread_call_idx = next(i for i, l in enumerate(lines) if i > try_idx and "unread_count()" in l)
        except_idx = next(i for i, l in enumerate(lines) if i > unread_call_idx and "except OSError:" in l)
        assert unread_init_idx < try_idx < unread_call_idx < except_idx


# ── E2E-style integration test ───────────────────────────────────


class TestCrashRecoveryE2EFlow:
    """Integration-style test verifying the full crash recovery → recovery_note flow."""

    def test_heartbeat_crash_recovery_creates_note_with_correct_content(self, tmp_path: Path):
        """Simulate full crash recovery for heartbeat and verify note content."""
        from core.supervisor.runner import AnimaRunner

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        anima_dir = animas_dir / "e2e-anima"
        anima_dir.mkdir()
        (anima_dir / "state").mkdir()
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()

        runner = AnimaRunner(
            anima_name="e2e-anima",
            socket_path=tmp_path / "test.sock",
            animas_dir=animas_dir,
            shared_dir=shared_dir,
        )
        runner.anima = MagicMock()

        recovery = _FakeRecovery(
            trigger="heartbeat",
            recovered_text="This was being generated when the process was killed by OOM.",
            tool_calls=[
                {"tool": "search_memory", "args": {}},
                {"tool": "read_file", "args": {"path": "/test"}},
            ],
            started_at="2026-03-05T10:30:00+09:00",
            last_event_at="2026-03-05T10:35:22+09:00",
        )

        with (
            patch(
                "core.memory.streaming_journal.StreamingJournal.list_orphan_thread_ids",
                return_value=["default"],
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.recover",
                return_value=recovery,
            ),
            patch(
                "core.memory.streaming_journal.StreamingJournal.confirm_recovery",
            ),
            patch("core.memory.activity.ActivityLogger"),
        ):
            runner._recover_streaming_journal()

        note_path = anima_dir / "state" / "recovery_note.md"
        assert note_path.exists()
        content = note_path.read_text(encoding="utf-8")

        # Verify all expected fields
        assert "2026-03-05T10:35:22+09:00" in content  # last_event_at preferred
        assert str(len(recovery.recovered_text)) in content
        assert "2" in content  # 2 tool calls
        assert "heartbeat" in content
