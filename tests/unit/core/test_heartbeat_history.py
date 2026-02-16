"""Unit tests for heartbeat history date-split and purge in core/anima.py."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.schemas import CycleResult


# ── Helpers ───────────────────────────────────────────────


def _make_digital_anima(anima_dir: Path, shared_dir: Path):
    """Create a DigitalAnima with all heavy deps mocked."""
    with patch("core.anima.AgentCore"), \
         patch("core.anima.MemoryManager") as MockMM, \
         patch("core.anima.Messenger"):
        MockMM.return_value.read_model_config.return_value = MagicMock()
        from core.anima import DigitalAnima
        return DigitalAnima(anima_dir, shared_dir)


def _make_cycle_result(**kwargs) -> CycleResult:
    defaults = dict(
        trigger="heartbeat",
        action="checked",
        summary="All systems normal",
        duration_ms=150,
    )
    defaults.update(kwargs)
    return CycleResult(**defaults)


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


# ── TestHeartbeatHistory ──────────────────────────────────


class TestHeartbeatHistory:
    """Tests for _save_heartbeat_history, _load_heartbeat_history, and _purge_old_heartbeat_logs."""

    def test_save_creates_date_split_file(self, dp, anima_dir):
        """Saving creates {date}.jsonl in heartbeat_history/ directory."""
        result = _make_cycle_result(summary="First heartbeat")
        dp._save_heartbeat_history(result)

        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        assert history_dir.exists()

        today_file = history_dir / f"{date.today().isoformat()}.jsonl"
        assert today_file.exists()

        content = today_file.read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert entry["summary"] == "First heartbeat"
        assert entry["trigger"] == "heartbeat"
        assert entry["action"] == "checked"
        assert entry["duration_ms"] == 150
        assert "timestamp" in entry

    def test_save_appends_to_existing(self, dp, anima_dir):
        """Multiple saves to same date append lines."""
        result1 = _make_cycle_result(summary="First")
        result2 = _make_cycle_result(summary="Second")
        result3 = _make_cycle_result(summary="Third")

        dp._save_heartbeat_history(result1)
        dp._save_heartbeat_history(result2)
        dp._save_heartbeat_history(result3)

        today_file = (
            anima_dir / "shortterm" / "heartbeat_history"
            / f"{date.today().isoformat()}.jsonl"
        )
        lines = today_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3

        summaries = [json.loads(line)["summary"] for line in lines]
        assert summaries == ["First", "Second", "Third"]

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

    def test_max_lines_truncation(self, dp, anima_dir):
        """Files are truncated to _HEARTBEAT_HISTORY_MAX_LINES."""
        # Override max lines to a small number for testing
        original_max = dp._HEARTBEAT_HISTORY_MAX_LINES
        try:
            # Use class-level override
            type(dp)._HEARTBEAT_HISTORY_MAX_LINES = 5

            # Write 10 entries by calling _save_heartbeat_history repeatedly
            for i in range(10):
                result = _make_cycle_result(summary=f"Entry {i}")
                dp._save_heartbeat_history(result)

            today_file = (
                anima_dir / "shortterm" / "heartbeat_history"
                / f"{date.today().isoformat()}.jsonl"
            )
            lines = today_file.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 5

            # Should keep the most recent entries (the last 5)
            summaries = [json.loads(line)["summary"] for line in lines]
            assert summaries[-1] == "Entry 9"
            assert summaries[0] == "Entry 5"
        finally:
            type(dp)._HEARTBEAT_HISTORY_MAX_LINES = original_max

    def test_purge_removes_old_files(self, dp, anima_dir):
        """Files older than retention period are deleted."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        # Create a file that is within retention (today)
        recent_date = date.today()
        (history_dir / f"{recent_date.isoformat()}.jsonl").write_text(
            '{"timestamp":"2026-02-16T10:00:00","trigger":"heartbeat",'
            '"action":"checked","summary":"recent","duration_ms":100}\n',
            encoding="utf-8",
        )

        # Create a file that is beyond retention
        old_date = date.today() - timedelta(days=dp._HEARTBEAT_HISTORY_RETENTION_DAYS + 5)
        (history_dir / f"{old_date.isoformat()}.jsonl").write_text(
            '{"timestamp":"old","trigger":"heartbeat",'
            '"action":"checked","summary":"old","duration_ms":100}\n',
            encoding="utf-8",
        )

        dp._purge_old_heartbeat_logs(history_dir)

        # Recent file should remain
        assert (history_dir / f"{recent_date.isoformat()}.jsonl").exists()
        # Old file should be deleted
        assert not (history_dir / f"{old_date.isoformat()}.jsonl").exists()

    def test_purge_keeps_recent_files(self, dp, anima_dir):
        """Files within retention period are not deleted."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        # Create several files within retention
        for days_ago in range(5):
            file_date = date.today() - timedelta(days=days_ago)
            (history_dir / f"{file_date.isoformat()}.jsonl").write_text(
                '{"data":"test"}\n', encoding="utf-8",
            )

        dp._purge_old_heartbeat_logs(history_dir)

        remaining = list(history_dir.glob("*.jsonl"))
        assert len(remaining) == 5

    def test_purge_ignores_non_date_filenames(self, dp, anima_dir):
        """Files that do not have ISO date stems are skipped, not deleted."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        (history_dir / "not-a-date.jsonl").write_text(
            '{"data":"test"}\n', encoding="utf-8",
        )
        (history_dir / f"{date.today().isoformat()}.jsonl").write_text(
            '{"data":"test"}\n', encoding="utf-8",
        )

        dp._purge_old_heartbeat_logs(history_dir)

        # Both should still exist -- non-date files are skipped (ValueError caught)
        assert (history_dir / "not-a-date.jsonl").exists()
        assert (history_dir / f"{date.today().isoformat()}.jsonl").exists()

    def test_save_triggers_purge(self, dp, anima_dir):
        """_save_heartbeat_history calls _purge_old_heartbeat_logs."""
        history_dir = anima_dir / "shortterm" / "heartbeat_history"
        history_dir.mkdir(parents=True)

        # Create an old file beyond retention
        old_date = date.today() - timedelta(days=dp._HEARTBEAT_HISTORY_RETENTION_DAYS + 1)
        old_file = history_dir / f"{old_date.isoformat()}.jsonl"
        old_file.write_text('{"data":"old"}\n', encoding="utf-8")

        # Saving should trigger purge
        result = _make_cycle_result(summary="New entry")
        dp._save_heartbeat_history(result)

        # Old file should be gone
        assert not old_file.exists()
        # Today's file should exist
        assert (history_dir / f"{date.today().isoformat()}.jsonl").exists()

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

    def test_save_summary_truncated_at_500_chars(self, dp, anima_dir):
        """Summary in saved entry is truncated to 500 characters."""
        long_summary = "x" * 1000
        result = _make_cycle_result(summary=long_summary)
        dp._save_heartbeat_history(result)

        today_file = (
            anima_dir / "shortterm" / "heartbeat_history"
            / f"{date.today().isoformat()}.jsonl"
        )
        content = today_file.read_text(encoding="utf-8").strip()
        entry = json.loads(content)
        assert len(entry["summary"]) == 500
