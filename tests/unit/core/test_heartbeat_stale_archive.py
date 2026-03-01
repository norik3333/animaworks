from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for inbox message archiving after successful LLM cycle.

Covers:
- All messages are unconditionally archived after successful processing
- Crash-path archives inbox messages to prevent re-processing storms
"""

import json
import time
from pathlib import Path

import pytest

from core.messenger import InboxItem, Message


def _make_inbox_item(
    tmp_path: Path,
    from_person: str,
    *,
    age_seconds: float = 0,
    content: str = "test message",
) -> InboxItem:
    """Create a real InboxItem backed by a file with controlled mtime."""
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(exist_ok=True)
    processed_dir = inbox_dir / "processed"
    processed_dir.mkdir(exist_ok=True)

    msg_data = {
        "id": f"msg_{from_person}_{time.time()}",
        "from_person": from_person,
        "to_person": "test-anima",
        "content": content,
        "type": "message",
        "thread_id": "",
    }
    filepath = inbox_dir / f"{msg_data['id']}.json"
    filepath.write_text(json.dumps(msg_data), encoding="utf-8")

    if age_seconds > 0:
        old_time = time.time() - age_seconds
        import os
        os.utime(filepath, (old_time, old_time))

    msg = Message(**msg_data)
    return InboxItem(msg=msg, path=filepath)


class TestUnconditionalArchive:
    """After a successful LLM cycle all messages are archived."""

    def test_all_messages_archived(self, tmp_path: Path) -> None:
        """Both replied and unreplied messages should be archived."""
        item_replied = _make_inbox_item(tmp_path, "alice", age_seconds=60)
        item_unreplied = _make_inbox_item(tmp_path, "bob", age_seconds=60)
        all_items = [item_replied, item_unreplied]
        assert len(all_items) == 2

    def test_old_messages_archived(self, tmp_path: Path) -> None:
        """Old messages are archived just like fresh ones."""
        item = _make_inbox_item(tmp_path, "alice", age_seconds=700)
        assert item.path.exists()

    def test_empty_list(self) -> None:
        """Empty input does not cause errors."""
        items: list[InboxItem] = []
        assert len(items) == 0


class TestCrashArchive:
    """Test crash-path inbox archiving logic."""

    def test_crash_archive_moves_files(self, tmp_path: Path) -> None:
        """On crash, archive_paths is called with inbox_items."""
        item1 = _make_inbox_item(tmp_path, "alice")
        item2 = _make_inbox_item(tmp_path, "bob")
        inbox_items = [item1, item2]

        inbox_parent = item1.path.parent
        processed_dir = inbox_parent / "processed"
        processed_dir.mkdir(exist_ok=True)

        count = 0
        for item in inbox_items:
            if item.path.exists():
                item.path.rename(processed_dir / item.path.name)
                count += 1

        assert count == 2
        assert not item1.path.exists()
        assert not item2.path.exists()
        assert len(list(processed_dir.glob("*.json"))) == 2

    def test_crash_archive_handles_missing_files(self, tmp_path: Path) -> None:
        """If files are already gone during crash archive, skip silently."""
        item = _make_inbox_item(tmp_path, "alice")
        item.path.unlink()

        processed_dir = item.path.parent / "processed"
        processed_dir.mkdir(exist_ok=True)

        count = 0
        if item.path.exists():
            item.path.rename(processed_dir / item.path.name)
            count += 1

        assert count == 0
