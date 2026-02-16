"""Unit tests for reconcile_message_log() in core/messenger.py."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from core.messenger import reconcile_message_log
from core.schemas import Message


@pytest.fixture
def shared_dir(tmp_path: Path) -> Path:
    d = tmp_path / "shared"
    d.mkdir()
    return d


def _create_processed_message(
    shared_dir: Path,
    *,
    anima: str = "alice",
    from_person: str = "bob",
    to_person: str = "alice",
    content: str = "hello",
    msg_id: str | None = None,
    thread_id: str | None = None,
    timestamp: datetime | None = None,
) -> Message:
    """Helper: create a processed message file under shared/inbox/{anima}/processed/."""
    msg = Message(
        from_person=from_person,
        to_person=to_person,
        content=content,
    )
    if msg_id is not None:
        msg.id = msg_id
    if thread_id is not None:
        msg.thread_id = thread_id
    else:
        msg.thread_id = msg.id
    if timestamp is not None:
        msg.timestamp = timestamp

    processed_dir = shared_dir / "inbox" / anima / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    filepath = processed_dir / f"{msg.id}.json"
    filepath.write_text(msg.model_dump_json(indent=2), encoding="utf-8")
    return msg


# ── Basic Reconciliation ─────────────────────────────────


class TestReconcileFindsUnloggedMessages:
    def test_finds_single_unlogged_message(self, shared_dir: Path) -> None:
        msg = _create_processed_message(shared_dir, content="unlogged message")
        count = reconcile_message_log(shared_dir)
        assert count == 1

        # Verify log entry was created
        log_dir = shared_dir / "message_log"
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["message_id"] == msg.id

    def test_finds_multiple_unlogged_messages(self, shared_dir: Path) -> None:
        _create_processed_message(shared_dir, msg_id="msg-001", content="first")
        _create_processed_message(shared_dir, msg_id="msg-002", content="second")
        count = reconcile_message_log(shared_dir)
        assert count == 2

    def test_finds_messages_across_multiple_animas(self, shared_dir: Path) -> None:
        _create_processed_message(
            shared_dir, anima="alice", from_person="bob",
            to_person="alice", msg_id="msg-a", content="to alice",
        )
        _create_processed_message(
            shared_dir, anima="bob", from_person="alice",
            to_person="bob", msg_id="msg-b", content="to bob",
        )
        count = reconcile_message_log(shared_dir)
        assert count == 2


# ── Deduplication ────────────────────────────────────────


class TestReconcileDeduplication:
    def test_already_logged_messages_not_duplicated(self, shared_dir: Path) -> None:
        msg = _create_processed_message(
            shared_dir, msg_id="msg-existing", content="already logged",
        )

        # Pre-populate message_log with this message
        log_dir = shared_dir / "message_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{msg.timestamp.date().isoformat()}.jsonl"
        entry = json.dumps({
            "timestamp": msg.timestamp.isoformat(),
            "from_person": msg.from_person,
            "to_person": msg.to_person,
            "type": msg.type,
            "summary": msg.content[:200],
            "message_id": msg.id,
            "thread_id": msg.thread_id,
        }, ensure_ascii=False)
        log_file.write_text(entry + "\n", encoding="utf-8")

        count = reconcile_message_log(shared_dir)
        assert count == 0

        # Verify no duplicate lines
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1

    def test_mixed_logged_and_unlogged(self, shared_dir: Path) -> None:
        msg_logged = _create_processed_message(
            shared_dir, msg_id="msg-logged", content="already tracked",
        )
        _create_processed_message(
            shared_dir, msg_id="msg-new", content="not yet tracked",
        )

        # Pre-populate only the first message
        log_dir = shared_dir / "message_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{msg_logged.timestamp.date().isoformat()}.jsonl"
        entry = json.dumps({
            "timestamp": msg_logged.timestamp.isoformat(),
            "from_person": msg_logged.from_person,
            "to_person": msg_logged.to_person,
            "type": msg_logged.type,
            "summary": msg_logged.content[:200],
            "message_id": msg_logged.id,
            "thread_id": msg_logged.thread_id,
        }, ensure_ascii=False)
        log_file.write_text(entry + "\n", encoding="utf-8")

        count = reconcile_message_log(shared_dir)
        assert count == 1

    def test_idempotent_on_repeated_calls(self, shared_dir: Path) -> None:
        _create_processed_message(shared_dir, msg_id="msg-idem", content="test")
        first = reconcile_message_log(shared_dir)
        assert first == 1
        second = reconcile_message_log(shared_dir)
        assert second == 0


# ── Empty / Missing State ────────────────────────────────


class TestReconcileEmptyState:
    def test_empty_inbox_produces_zero(self, shared_dir: Path) -> None:
        # inbox exists but no processed dirs
        (shared_dir / "inbox").mkdir(parents=True, exist_ok=True)
        count = reconcile_message_log(shared_dir)
        assert count == 0

    def test_no_inbox_dir_produces_zero(self, shared_dir: Path) -> None:
        # shared_dir exists but no inbox at all
        count = reconcile_message_log(shared_dir)
        assert count == 0

    def test_empty_processed_dir_produces_zero(self, shared_dir: Path) -> None:
        processed = shared_dir / "inbox" / "alice" / "processed"
        processed.mkdir(parents=True, exist_ok=True)
        count = reconcile_message_log(shared_dir)
        assert count == 0


# ── Entry Format ─────────────────────────────────────────


class TestReconcileEntryFormat:
    def test_entry_format_matches_append_message_log(self, shared_dir: Path) -> None:
        """Verify reconciled entries have the same fields as _append_message_log."""
        msg = _create_processed_message(
            shared_dir,
            msg_id="msg-fmt",
            from_person="bob",
            to_person="alice",
            content="format check",
            thread_id="thread-xyz",
        )

        reconcile_message_log(shared_dir)

        log_dir = shared_dir / "message_log"
        log_files = list(log_dir.glob("*.jsonl"))
        assert len(log_files) == 1
        lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])

        # Exact field set from _append_message_log
        expected_keys = {
            "timestamp", "from_person", "to_person",
            "type", "summary", "message_id", "thread_id",
        }
        assert set(entry.keys()) == expected_keys

        # Value checks
        assert entry["from_person"] == "bob"
        assert entry["to_person"] == "alice"
        assert entry["type"] == "message"
        assert entry["summary"] == "format check"
        assert entry["message_id"] == "msg-fmt"
        assert entry["thread_id"] == "thread-xyz"
        assert entry["timestamp"] == msg.timestamp.isoformat()

    def test_summary_truncated_to_200_chars(self, shared_dir: Path) -> None:
        long_content = "A" * 500
        _create_processed_message(
            shared_dir, msg_id="msg-long", content=long_content,
        )

        reconcile_message_log(shared_dir)

        log_dir = shared_dir / "message_log"
        log_files = list(log_dir.glob("*.jsonl"))
        lines = log_files[0].read_text(encoding="utf-8").strip().splitlines()
        entry = json.loads(lines[0])
        assert len(entry["summary"]) == 200

    def test_log_file_named_by_message_date(self, shared_dir: Path) -> None:
        msg = _create_processed_message(shared_dir, msg_id="msg-date")
        reconcile_message_log(shared_dir)

        expected_filename = f"{msg.timestamp.date().isoformat()}.jsonl"
        log_file = shared_dir / "message_log" / expected_filename
        assert log_file.exists()

    def test_malformed_message_file_skipped(self, shared_dir: Path) -> None:
        # Create a valid message
        _create_processed_message(shared_dir, msg_id="msg-valid", content="valid")
        # Create a malformed file
        processed = shared_dir / "inbox" / "alice" / "processed"
        (processed / "bad.json").write_text("not valid json", encoding="utf-8")

        count = reconcile_message_log(shared_dir)
        assert count == 1  # Only the valid message is reconciled
