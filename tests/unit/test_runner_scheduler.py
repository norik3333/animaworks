"""Unit tests for PersonRunner autonomous scheduler."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunnerSchedulerSetup:
    """Tests for PersonRunner scheduler initialization."""

    def _make_runner(self, tmp_path: Path):
        from core.supervisor.runner import PersonRunner

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir(exist_ok=True)
        person_dir = persons_dir / "test-person"
        person_dir.mkdir(exist_ok=True)
        (person_dir / "identity.md").write_text("test")
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(exist_ok=True)
        socket_path = tmp_path / "test.sock"

        return PersonRunner(
            person_name="test-person",
            socket_path=socket_path,
            persons_dir=persons_dir,
            shared_dir=shared_dir,
        )

    def test_scheduler_initially_none(self, tmp_path):
        runner = self._make_runner(tmp_path)
        assert runner.scheduler is None

    @pytest.mark.asyncio
    async def test_setup_scheduler_creates_scheduler(self, tmp_path):
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.memory.read_heartbeat_config.return_value = "5分ごと\n8:00 - 23:00"
        mock_person.memory.read_cron_config.return_value = ""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()

        assert runner.scheduler is not None
        assert runner.scheduler.running
        # Should have heartbeat job registered
        jobs = runner.scheduler.get_jobs()
        assert len(jobs) >= 1
        assert any("heartbeat" in j.id for j in jobs)

        runner.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_setup_scheduler_with_cron_tasks(self, tmp_path):
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.name = "test-person"
        mock_person.memory.read_heartbeat_config.return_value = "30分ごと\n9:00 - 22:00"
        mock_person.memory.read_cron_config.return_value = """## Task A（毎日 9:00 JST）
type: llm
Do something
"""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()

        jobs = runner.scheduler.get_jobs()
        job_ids = [j.id for j in jobs]
        assert "test-person_heartbeat" in job_ids
        assert "test-person_cron_0" in job_ids

        runner.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_setup_scheduler_no_heartbeat_config(self, tmp_path):
        """Scheduler should start even without heartbeat.md content."""
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.memory.read_heartbeat_config.return_value = ""
        mock_person.memory.read_cron_config.return_value = ""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()

        assert runner.scheduler is not None
        assert runner.scheduler.running
        # No jobs since no config
        assert len(runner.scheduler.get_jobs()) == 0

        runner.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_setup_scheduler_handles_error_gracefully(self, tmp_path):
        """Scheduler setup should not crash on errors."""
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.memory.read_heartbeat_config.side_effect = Exception("file error")
        runner.person = mock_person

        # Should not raise
        runner._setup_scheduler()
        # Scheduler should be None after error
        assert runner.scheduler is None

    @pytest.mark.asyncio
    async def test_reload_schedule(self, tmp_path):
        """Test hot-reload of schedule from disk."""
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.memory.read_heartbeat_config.return_value = "5分ごと\n8:00 - 23:00"
        mock_person.memory.read_cron_config.return_value = ""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()
        initial_jobs = len(runner.scheduler.get_jobs())
        assert initial_jobs == 1  # heartbeat only

        # Now add cron config for reload
        mock_person.memory.read_cron_config.return_value = """## New Task（毎日 10:00 JST）
type: llm
New task description
"""
        result = runner._reload_schedule("test-person")
        assert result["removed"] == 1
        assert len(result["new_jobs"]) == 2  # heartbeat + cron

        runner.scheduler.shutdown(wait=False)

    @pytest.mark.asyncio
    async def test_get_status_includes_scheduler_info(self, tmp_path):
        """get_status should include scheduler_running and scheduler_jobs."""
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person._status = "idle"
        mock_person._current_task = None
        mock_person.needs_bootstrap = False
        mock_person.memory.read_heartbeat_config.return_value = "5分ごと\n8:00 - 23:00"
        mock_person.memory.read_cron_config.return_value = ""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()

        result = await runner._handle_get_status({})
        assert result["scheduler_running"] is True
        assert result["scheduler_jobs"] == 1

        runner.scheduler.shutdown(wait=False)


class TestRunnerSchedulerCleanup:
    """Tests for scheduler cleanup on shutdown."""

    def _make_runner(self, tmp_path: Path):
        from core.supervisor.runner import PersonRunner

        persons_dir = tmp_path / "persons"
        persons_dir.mkdir(exist_ok=True)
        (persons_dir / "test-person").mkdir(exist_ok=True)
        (persons_dir / "test-person" / "identity.md").write_text("test")
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(exist_ok=True)
        socket_path = tmp_path / "test.sock"

        return PersonRunner(
            person_name="test-person",
            socket_path=socket_path,
            persons_dir=persons_dir,
            shared_dir=shared_dir,
        )

    @pytest.mark.asyncio
    async def test_cleanup_shuts_down_scheduler(self, tmp_path):
        runner = self._make_runner(tmp_path)
        mock_person = MagicMock()
        mock_person.memory.read_heartbeat_config.return_value = "5分ごと\n8:00 - 23:00"
        mock_person.memory.read_cron_config.return_value = ""
        mock_person.set_on_schedule_changed = MagicMock()
        runner.person = mock_person

        runner._setup_scheduler()
        assert runner.scheduler.running

        await runner._cleanup()
        # AsyncIOScheduler.shutdown(wait=False) defers actual stop to the
        # event loop; yield control so the scheduler can finalize.
        await asyncio.sleep(0.1)
        assert not runner.scheduler.running
