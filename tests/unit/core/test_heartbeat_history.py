# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for heartbeat history loading in core/anima.py.

Note: _save_heartbeat_history and _purge_old_heartbeat_logs were removed
as part of the unified activity log migration.  Writing is now handled by
ActivityLogger.  Only the read-side (_load_heartbeat_history) remains for
backward compatibility with existing heartbeat_history/ files.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────


def _make_digital_anima(anima_dir: Path, shared_dir: Path):
    """Create a DigitalAnima with all heavy deps mocked."""
    with patch("core.anima.AgentCore"), \
         patch("core.anima.MemoryManager") as MockMM, \
         patch("core.anima.Messenger"):
        MockMM.return_value.read_model_config.return_value = MagicMock()
        from core.anima import DigitalAnima
        return DigitalAnima(anima_dir, shared_dir)


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "alice"
    d.mkdir(parents=True)
    (d / "identity.md").write_text("# Alice", encoding="utf-8")
    return d


@pytest.fixture
def shared_dir(tmp_path: Path) -> Path:
    d = tmp_path / "shared"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def dp(anima_dir: Path, shared_dir: Path):
    """A DigitalAnima instance with mocked dependencies."""
    return _make_digital_anima(anima_dir, shared_dir)


# ── TestHeartbeatHistoryLoad ─────────────────────────────


class TestHeartbeatHistoryLoad:
    """Tests for _load_heartbeat_history (read-only, backward compat)."""

    def test_load_from_date_split(self, dp, anima_dir):
        """Loading reads from date-split directory."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        # Write entries for today
        entries = []
        for i in range(5):
            entry = json.dumps({
                "timestamp": f"2026-02-16T{10 + i:02d}:00:00",
                "trigger": "heartbeat",
                "action": "checked",
                "summary": f"Entry {i}",
                "duration_ms": 100,
            }, ensure_ascii=False)
            entries.append(entry)
        (history_dir / f"{date.today().isoformat()}.jsonl").write_text(
            "\n".join(entries) + "\n", encoding="utf-8",
        )

        text = dp._load_heartbeat_history()
        assert text != ""
        # Should contain at most _HEARTBEAT_HISTORY_N entries (default 3)
        lines = text.strip().splitlines()
        assert len(lines) == dp._HEARTBEAT_HISTORY_N
        # Should be the last N entries
        assert "Entry 4" in lines[-1]
        assert "Entry 3" in lines[-2]
        assert "Entry 2" in lines[-3]

    def test_load_fallback_legacy(self, dp, anima_dir):
        """Loading falls back to legacy single file if no directory."""
        shortterm_dir = anima_dir / "shortterm"
        shortterm_dir.mkdir(parents=True, exist_ok=True)
        # No heartbeat_history/ directory

        entry = json.dumps({
            "timestamp": "2026-02-16T08:00:00",
            "trigger": "heartbeat",
            "action": "scanned",
            "summary": "Legacy heartbeat",
            "duration_ms": 120,
        }, ensure_ascii=False)
        (shortterm_dir / "heartbeat_history.jsonl").write_text(
            entry + "\n", encoding="utf-8",
        )

        text = dp._load_heartbeat_history()
        assert text != ""
        assert "Legacy heartbeat" in text
        assert "[scanned]" in text

    def test_load_returns_empty_when_no_files(self, dp, anima_dir):
        """Loading returns empty string when neither directory nor legacy file exists."""
        text = dp._load_heartbeat_history()
        assert text == ""

    def test_load_across_multiple_days(self, dp, anima_dir):
        """Loading reads entries from multiple recent day files."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        # Write one entry per day for 3 days
        for days_ago in range(3):
            file_date = date.today() - timedelta(days=days_ago)
            entry = json.dumps({
                "timestamp": f"2026-02-{16 - days_ago}T10:00:00",
                "trigger": "heartbeat",
                "action": "checked",
                "summary": f"Day {days_ago} ago",
                "duration_ms": 100,
            }, ensure_ascii=False)
            (history_dir / f"{file_date.isoformat()}.jsonl").write_text(
                entry + "\n", encoding="utf-8",
            )

        text = dp._load_heartbeat_history()
        assert text != ""
        lines = text.strip().splitlines()
        # _HEARTBEAT_HISTORY_N is 3, and we have 3 entries total
        assert len(lines) == 3
