"""Unit tests for messaging data model unification.

Verifies:
1. Event type alias resolution (_resolve_type_filter)
2. messenger.send() records message_sent with from_type
3. messenger.send() no longer writes to dm_logs/
4. activity.py type_map contains unified labels
5. DM grouping handles both old and new event types
6. cascade_limiter uses new event types (via alias)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.memory.activity import (
    ActivityEntry,
    ActivityLogger,
    _EVENT_TYPE_ALIASES,
    _resolve_type_filter,
)


# ── _resolve_type_filter ─────────────────────────────────

class TestResolveTypeFilter:
    """Verify alias expansion for type filters."""

    def test_none_returns_none(self) -> None:
        assert _resolve_type_filter(None) is None

    def test_new_name_includes_old(self) -> None:
        result = _resolve_type_filter(["message_sent"])
        assert "message_sent" in result
        assert "dm_sent" in result

    def test_old_name_includes_new(self) -> None:
        result = _resolve_type_filter(["dm_sent"])
        assert "dm_sent" in result
        assert "message_sent" in result

    def test_message_received_alias(self) -> None:
        result = _resolve_type_filter(["message_received"])
        assert "message_received" in result
        assert "dm_received" in result

    def test_dm_received_alias(self) -> None:
        result = _resolve_type_filter(["dm_received"])
        assert "dm_received" in result
        assert "message_received" in result

    def test_unrelated_type_not_expanded(self) -> None:
        result = _resolve_type_filter(["channel_post"])
        assert result == {"channel_post"}

    def test_mixed_types(self) -> None:
        result = _resolve_type_filter(["message_sent", "channel_post"])
        assert "message_sent" in result
        assert "dm_sent" in result
        assert "channel_post" in result

    def test_all_aliases_present(self) -> None:
        assert "dm_sent" in _EVENT_TYPE_ALIASES
        assert "dm_received" in _EVENT_TYPE_ALIASES


# ── ActivityLogger with aliases ──────────────────────────

class TestActivityLoggerAliasIntegration:
    """Verify that recent() with new types matches legacy log entries."""

    @pytest.fixture
    def anima_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "animas" / "test-anima"
        (d / "activity_log").mkdir(parents=True)
        return d

    def _write_entry(self, anima_dir: Path, entry: dict[str, Any]) -> None:
        from core.time_utils import now_jst
        today = now_jst().date().isoformat()
        path = anima_dir / "activity_log" / f"{today}.jsonl"
        line = json.dumps(entry, ensure_ascii=False)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def test_message_sent_matches_dm_sent(self, anima_dir: Path) -> None:
        from core.time_utils import now_iso
        self._write_entry(anima_dir, {
            "ts": now_iso(), "type": "dm_sent",
            "content": "legacy dm", "to": "bob",
        })
        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_sent"])
        assert len(entries) == 1
        assert entries[0].type == "dm_sent"

    def test_message_received_matches_dm_received(self, anima_dir: Path) -> None:
        from core.time_utils import now_iso
        self._write_entry(anima_dir, {
            "ts": now_iso(), "type": "dm_received",
            "content": "legacy dm", "from": "alice",
        })
        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_received"])
        assert len(entries) == 1
        assert entries[0].type == "dm_received"

    def test_new_message_sent_also_returned(self, anima_dir: Path) -> None:
        from core.time_utils import now_iso
        self._write_entry(anima_dir, {
            "ts": now_iso(), "type": "message_sent",
            "content": "new format", "to": "bob",
            "meta": {"from_type": "anima"},
        })
        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_sent"])
        assert len(entries) == 1
        assert entries[0].type == "message_sent"

    def test_mixed_old_and_new(self, anima_dir: Path) -> None:
        from core.time_utils import now_iso
        self._write_entry(anima_dir, {
            "ts": now_iso(), "type": "dm_sent",
            "content": "old", "to": "bob",
        })
        self._write_entry(anima_dir, {
            "ts": now_iso(), "type": "message_sent",
            "content": "new", "to": "bob",
            "meta": {"from_type": "anima"},
        })
        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_sent"])
        assert len(entries) == 2


# ── type_map unified labels ──────────────────────────────

class TestTypeMapUnified:
    """Verify type_map has correct unified labels."""

    def test_message_sent_label(self) -> None:
        entry = ActivityEntry(ts="2026-02-25T10:00:00+09:00", type="message_sent")
        formatted = ActivityLogger._format_entry(entry)
        assert "MSG>" in formatted

    def test_response_sent_label(self) -> None:
        entry = ActivityEntry(ts="2026-02-25T10:00:00+09:00", type="response_sent")
        formatted = ActivityLogger._format_entry(entry)
        assert "RESP>" in formatted

    def test_dm_sent_legacy_label(self) -> None:
        entry = ActivityEntry(ts="2026-02-25T10:00:00+09:00", type="dm_sent")
        formatted = ActivityLogger._format_entry(entry)
        assert "MSG>" in formatted

    def test_dm_received_legacy_label(self) -> None:
        entry = ActivityEntry(ts="2026-02-25T10:00:00+09:00", type="dm_received")
        formatted = ActivityLogger._format_entry(entry)
        assert "MSG<" in formatted


# ── DM grouping with new types ───────────────────────────

class TestDMGroupingUnified:
    """Verify grouping logic handles both old and new event types."""

    def test_groups_message_sent(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="message_sent",
                to_person="bob", meta={"from_type": "anima"},
            ),
            ActivityEntry(
                ts="2026-02-25T10:01:00+09:00", type="message_received",
                from_person="bob", meta={"from_type": "anima"},
            ),
        ]
        groups = ActivityLogger._group_entries(entries)
        assert len(groups) == 1
        assert groups[0].type == "dm"
        assert len(groups[0].entries) == 2

    def test_groups_legacy_dm_sent(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="dm_sent",
                to_person="bob",
            ),
            ActivityEntry(
                ts="2026-02-25T10:01:00+09:00", type="dm_received",
                from_person="bob",
            ),
        ]
        groups = ActivityLogger._group_entries(entries)
        assert len(groups) == 1
        assert groups[0].type == "dm"

    def test_human_message_received_not_grouped_as_dm(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="message_received",
                from_person="human", channel="chat",
                meta={"from_type": "human"},
            ),
        ]
        groups = ActivityLogger._group_entries(entries)
        assert len(groups) == 1
        assert groups[0].type == "single"

    def test_mixed_old_new_grouped_by_peer(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="dm_sent",
                to_person="bob",
            ),
            ActivityEntry(
                ts="2026-02-25T10:01:00+09:00", type="message_sent",
                to_person="bob", meta={"from_type": "anima"},
            ),
        ]
        groups = ActivityLogger._group_entries(entries)
        assert len(groups) == 1
        assert groups[0].type == "dm"
        assert len(groups[0].entries) == 2


# ── messenger.send() event name & dm_logs ────────────────

class TestMessengerSendUnified:
    """Verify messenger.send() uses message_sent and skips dm_logs."""

    @pytest.fixture
    def shared_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "shared"
        d.mkdir()
        return d

    @pytest.fixture
    def anima_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "animas" / "alice"
        (d / "activity_log").mkdir(parents=True)
        return d

    def test_send_records_message_sent(
        self, shared_dir: Path, anima_dir: Path,
    ) -> None:
        from core.messenger import Messenger
        m = Messenger(shared_dir, "alice")
        m.send("bob", "Hello Bob!")

        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_sent"])
        assert len(entries) == 1
        assert entries[0].type == "message_sent"
        assert entries[0].meta.get("from_type") == "anima"

    def test_send_does_not_write_dm_logs(
        self, shared_dir: Path, anima_dir: Path,
    ) -> None:
        from core.messenger import Messenger
        m = Messenger(shared_dir, "alice")
        m.send("bob", "Hello Bob!")

        dm_logs = shared_dir / "dm_logs"
        if dm_logs.exists():
            files = list(dm_logs.glob("*.jsonl"))
            for f in files:
                content = f.read_text(encoding="utf-8").strip()
                assert content == "", f"dm_logs should not have new entries: {f}"

    def test_send_with_intent_in_meta(
        self, shared_dir: Path, anima_dir: Path,
    ) -> None:
        from core.messenger import Messenger
        m = Messenger(shared_dir, "alice")
        m.send("bob", "Report", intent="report")

        activity = ActivityLogger(anima_dir)
        entries = activity.recent(days=1, types=["message_sent"])
        assert len(entries) == 1
        assert entries[0].meta.get("intent") == "report"
        assert entries[0].meta.get("from_type") == "anima"


# ── cascade_limiter event names ──────────────────────────

class TestCascadeLimiterEventNames:
    """Verify cascade_limiter queries new event types."""

    @pytest.fixture
    def anima_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "animas" / "alice"
        (d / "activity_log").mkdir(parents=True)
        return d

    def test_counts_legacy_dm_entries(self, anima_dir: Path) -> None:
        from core.time_utils import now_iso
        activity = ActivityLogger(anima_dir)
        for _ in range(3):
            activity.log("dm_sent", content="hi", to_person="bob")
        for _ in range(3):
            activity.log("dm_received", content="hi", from_person="bob")

        from core.cascade_limiter import ConversationDepthLimiter
        limiter = ConversationDepthLimiter(window_s=600, max_depth=6)
        depth = limiter.current_depth("alice", "bob", anima_dir)
        assert depth == 6

    def test_counts_new_message_entries(self, anima_dir: Path) -> None:
        activity = ActivityLogger(anima_dir)
        for _ in range(3):
            activity.log("message_sent", content="hi", to_person="bob",
                         meta={"from_type": "anima"})
        for _ in range(3):
            activity.log("message_received", content="hi", from_person="bob",
                         meta={"from_type": "anima"})

        from core.cascade_limiter import ConversationDepthLimiter
        limiter = ConversationDepthLimiter(window_s=600, max_depth=6)
        depth = limiter.current_depth("alice", "bob", anima_dir)
        assert depth == 6

    def test_counts_mixed_old_new(self, anima_dir: Path) -> None:
        activity = ActivityLogger(anima_dir)
        activity.log("dm_sent", content="old", to_person="bob")
        activity.log("message_sent", content="new", to_person="bob",
                     meta={"from_type": "anima"})
        activity.log("dm_received", content="old", from_person="bob")
        activity.log("message_received", content="new", from_person="bob",
                     meta={"from_type": "anima"})

        from core.cascade_limiter import ConversationDepthLimiter
        limiter = ConversationDepthLimiter(window_s=600, max_depth=6)
        depth = limiter.current_depth("alice", "bob", anima_dir)
        assert depth == 4


# ── format_for_priming unified display ───────────────────

class TestFormatForPrimingUnified:
    """Verify format_for_priming uses unified display format."""

    def test_message_sent_shows_msg_arrow(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="message_sent",
                content="hello", to_person="bob",
                meta={"from_type": "anima"},
            ),
        ]
        activity = ActivityLogger(Path("/tmp/fake"))
        result = activity.format_for_priming(entries)
        assert "MSG>" in result

    def test_response_sent_shows_resp(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="response_sent",
                content="hello", to_person="human",
            ),
        ]
        activity = ActivityLogger(Path("/tmp/fake"))
        result = activity.format_for_priming(entries)
        assert "RESP>" in result

    def test_dm_sent_legacy_shows_msg_arrow(self) -> None:
        entries = [
            ActivityEntry(
                ts="2026-02-25T10:00:00+09:00", type="dm_sent",
                content="legacy hello", to_person="bob",
            ),
        ]
        activity = ActivityLogger(Path("/tmp/fake"))
        result = activity.format_for_priming(entries)
        assert "MSG>" in result


# ── response_sent unchanged ──────────────────────────────

class TestResponseSentUnchanged:
    """Verify response_sent event type is maintained."""

    def test_response_sent_exists_in_code(self) -> None:
        import inspect
        from core.memory.activity import ActivityLogger
        source = inspect.getsource(ActivityLogger._format_entry)
        assert '"response_sent"' in source
