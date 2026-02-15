"""Unit tests for server/routes/system.py — System endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server.routes.system import _parse_cron_jobs


def _make_test_app(
    persons: dict | None = None,
    persons_dir: Path | None = None,
    shared_dir: Path | None = None,
    person_names: list[str] | None = None,
):
    from fastapi import FastAPI
    from server.routes.system import create_system_router

    app = FastAPI()
    app.state.persons_dir = persons_dir or Path("/tmp/fake/persons")
    app.state.shared_dir = shared_dir or Path("/tmp/fake/shared")
    app.state.person_names = (
        person_names if person_names is not None
        else list((persons or {}).keys())
    )

    # Mock supervisor
    supervisor = MagicMock()
    supervisor.get_all_status.return_value = {}
    supervisor.get_process_status.return_value = {"status": "running", "pid": 1234}
    supervisor.is_scheduler_running.return_value = False
    supervisor.scheduler = None
    supervisor.start_person = AsyncMock()
    supervisor.stop_person = AsyncMock()
    supervisor.restart_person = AsyncMock()
    app.state.supervisor = supervisor

    # Mock ws_manager
    ws_manager = MagicMock()
    ws_manager.active_connections = []
    app.state.ws_manager = ws_manager

    router = create_system_router()
    app.include_router(router, prefix="/api")
    return app


# ── GET /shared/users ────────────────────────────────────


class TestListSharedUsers:
    async def test_no_users_dir(self, tmp_path):
        shared_dir = tmp_path / "shared"
        # Don't create users dir
        app = _make_test_app(shared_dir=shared_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shared/users")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_users(self, tmp_path):
        shared_dir = tmp_path / "shared"
        users_dir = shared_dir / "users"
        users_dir.mkdir(parents=True)
        (users_dir / "alice").mkdir()
        (users_dir / "bob").mkdir()
        # Also create a file (should be ignored)
        (users_dir / "readme.txt").write_text("ignore", encoding="utf-8")

        app = _make_test_app(shared_dir=shared_dir)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/shared/users")
        data = resp.json()
        assert "alice" in data
        assert "bob" in data
        assert "readme.txt" not in data


# ── GET /system/status ───────────────────────────────────


class TestSystemStatus:
    async def test_status(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])
        app.state.supervisor.get_all_status.return_value = {
            "alice": {"status": "running", "pid": 1234},
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")
        data = resp.json()
        assert data["persons"] == 1
        assert "processes" in data
        assert data["scheduler_running"] is False

    async def test_status_empty(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        app = _make_test_app(persons_dir=persons_dir, person_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")
        data = resp.json()
        assert data["persons"] == 0
        assert data["scheduler_running"] is False

    async def test_status_scheduler_running_with_cron(self, tmp_path):
        """scheduler_running should be True when cron.md has active jobs."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n## Morning Report (毎朝9時)\ntype: llm\nDo report\n",
            encoding="utf-8",
        )

        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])
        app.state.supervisor.is_scheduler_running.return_value = True
        app.state.supervisor.get_all_status.return_value = {
            "alice": {"status": "running", "pid": 1234},
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/status")
        data = resp.json()
        assert data["scheduler_running"] is True


# ── POST /system/reload ─────────────────────────────────


class TestReloadPersons:
    async def test_reload_adds_new_persons(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Create a new person on disk
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "identity.md").write_text("# Alice", encoding="utf-8")

        app = _make_test_app(
            persons={},
            persons_dir=persons_dir,
            shared_dir=shared_dir,
            person_names=[],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/system/reload")

        data = resp.json()
        assert "alice" in data["added"]
        assert data["total"] == 1

    async def test_reload_removes_deleted_persons(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        app = _make_test_app(
            persons={},
            persons_dir=persons_dir,
            shared_dir=shared_dir,
            person_names=["deleted"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/system/reload")

        data = resp.json()
        assert "deleted" in data["removed"]
        assert data["total"] == 0

    async def test_reload_refreshes_existing(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "identity.md").write_text("# Alice", encoding="utf-8")

        app = _make_test_app(
            persons={},
            persons_dir=persons_dir,
            shared_dir=shared_dir,
            person_names=["alice"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/system/reload")

        data = resp.json()
        assert "alice" in data["refreshed"]

    async def test_reload_no_persons_dir(self, tmp_path):
        persons_dir = tmp_path / "nonexistent"
        shared_dir = tmp_path / "shared"

        app = _make_test_app(
            persons={},
            persons_dir=persons_dir,
            shared_dir=shared_dir,
            person_names=[],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/system/reload")
        data = resp.json()
        assert data["total"] == 0

    async def test_reload_skips_disabled_person(self, tmp_path):
        """A person with status.json {enabled: false} is NOT added or started on reload."""
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        shared_dir = tmp_path / "shared"

        # Create person on disk with identity.md but disabled via status.json
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()
        (alice_dir / "identity.md").write_text("# Alice", encoding="utf-8")
        (alice_dir / "status.json").write_text(
            json.dumps({"enabled": False}), encoding="utf-8"
        )

        app = _make_test_app(
            persons={},
            persons_dir=persons_dir,
            shared_dir=shared_dir,
            person_names=[],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/system/reload")

        data = resp.json()
        # Disabled person should NOT be added
        assert "alice" not in data["added"]
        assert "alice" not in data["refreshed"]
        assert data["total"] == 0

        # start_person should NOT have been called
        app.state.supervisor.start_person.assert_not_awaited()


# ── GET /activity/recent ─────────────────────────────────


class TestRecentActivity:
    async def test_activity_no_persons(self):
        app = _make_test_app(person_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent")
        data = resp.json()
        assert data["events"] == []

    async def test_activity_with_hours_param(self):
        app = _make_test_app(person_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?hours=1")
        assert resp.status_code == 200

    async def test_activity_with_person_filter(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir()


        app = _make_test_app(
            persons_dir=persons_dir,
            person_names=["alice"],
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?person=alice")
        assert resp.status_code == 200


# ── GET /system/connections ──────────────────────────────


class TestSystemConnections:
    async def test_connections_with_active_clients(self):
        app = _make_test_app(person_names=["alice", "bob"])
        # Simulate 3 active websocket connections
        app.state.ws_manager.active_connections = [
            MagicMock(), MagicMock(), MagicMock(),
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/connections")
        data = resp.json()
        assert data["websocket"]["connected_clients"] == 3
        assert "alice" in data["processes"]
        assert "bob" in data["processes"]

    async def test_connections_without_active_connections_attr(self):
        app = _make_test_app(person_names=["alice"])
        # Remove active_connections attribute
        del app.state.ws_manager.active_connections

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/connections")
        data = resp.json()
        assert data["websocket"]["connected_clients"] == 0

    async def test_connections_empty(self):
        app = _make_test_app(person_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/connections")
        data = resp.json()
        assert data["websocket"]["connected_clients"] == 0
        assert data["processes"] == {}


# ── GET /system/scheduler ────────────────────────────────


class TestSystemScheduler:
    async def test_no_cron_files(self, tmp_path):
        """No cron.md files -> running=False, empty jobs."""
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is False
        assert data["person_jobs"] == []

    async def test_no_persons(self, tmp_path):
        """No registered persons -> running=False, empty jobs."""
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        app = _make_test_app(persons_dir=persons_dir, person_names=[])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is False
        assert data["person_jobs"] == []

    async def test_scheduler_with_cron_jobs(self, tmp_path):
        """cron.md with active jobs -> running=True, jobs populated."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Morning Report (毎朝9時)\n"
            "type: llm\n"
            "朝の報告をまとめる\n",
            encoding="utf-8",
        )

        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])
        app.state.supervisor.is_scheduler_running.return_value = True
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        app.state.supervisor.scheduler = mock_scheduler

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is True
        assert len(data["person_jobs"]) == 1
        job = data["person_jobs"][0]
        assert job["person"] == "alice"
        assert job["type"] == "llm"
        assert "Morning Report" in job["name"]
        assert job["schedule"] == "毎朝9時"
        assert job["next_run"] is None

    async def test_scheduler_multiple_persons(self, tmp_path):
        """Jobs from multiple persons are aggregated."""
        persons_dir = tmp_path / "persons"
        for name in ("alice", "bob"):
            d = persons_dir / name
            d.mkdir(parents=True)
            (d / "cron.md").write_text(
                f"# Cron: {name}\n\n## Task ({name} schedule)\ntype: llm\nDo work\n",
                encoding="utf-8",
            )

        app = _make_test_app(
            persons_dir=persons_dir, person_names=["alice", "bob"],
        )
        app.state.supervisor.is_scheduler_running.return_value = True
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        app.state.supervisor.scheduler = mock_scheduler

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is True
        assert len(data["person_jobs"]) == 2
        persons_in_jobs = {j["person"] for j in data["person_jobs"]}
        assert persons_in_jobs == {"alice", "bob"}

    async def test_scheduler_commented_sections_ignored(self, tmp_path):
        """Sections inside HTML comments should not produce jobs."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "<!--\n"
            "## Disabled Task (noon)\n"
            "type: llm\n"
            "Should be ignored\n"
            "-->\n",
            encoding="utf-8",
        )

        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is False
        assert data["person_jobs"] == []

    async def test_scheduler_mixed_active_and_commented(self, tmp_path):
        """Active jobs are returned; commented-out ones are skipped."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Active Task (every 5 min)\n"
            "type: llm\n"
            "Do active work\n\n"
            "<!--\n"
            "## Disabled Task (noon)\n"
            "type: llm\n"
            "Should be ignored\n"
            "-->\n",
            encoding="utf-8",
        )

        app = _make_test_app(persons_dir=persons_dir, person_names=["alice"])
        app.state.supervisor.is_scheduler_running.return_value = True
        mock_scheduler = MagicMock()
        mock_scheduler.get_jobs.return_value = []
        app.state.supervisor.scheduler = mock_scheduler

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/system/scheduler")
        data = resp.json()
        assert data["running"] is True
        assert len(data["person_jobs"]) == 1
        assert "Active Task" in data["person_jobs"][0]["name"]


# ── _parse_cron_jobs (unit) ────────────────────────────────


class TestParseCronJobs:
    def test_empty_persons_list(self, tmp_path):
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()
        assert _parse_cron_jobs(persons_dir, []) == []

    def test_no_cron_file(self, tmp_path):
        persons_dir = tmp_path / "persons"
        (persons_dir / "alice").mkdir(parents=True)
        assert _parse_cron_jobs(persons_dir, ["alice"]) == []

    def test_single_job(self, tmp_path):
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Daily Summary (毎日18時)\n"
            "type: llm\n"
            "まとめを作成する\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert len(jobs) == 1
        assert jobs[0]["person"] == "alice"
        assert jobs[0]["type"] == "llm"
        assert jobs[0]["schedule"] == "毎日18時"
        assert "Daily Summary" in jobs[0]["name"]
        assert jobs[0]["next_run"] is None
        assert jobs[0]["id"].startswith("cron-alice-")

    def test_multiple_jobs_same_person(self, tmp_path):
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Morning Report (毎朝9時)\n"
            "type: llm\n"
            "朝の報告\n\n"
            "## Evening Summary (毎夕18時)\n"
            "type: llm\n"
            "夕方のまとめ\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert len(jobs) == 2
        assert jobs[0]["name"] == "Morning Report (毎朝9時)"
        assert jobs[1]["name"] == "Evening Summary (毎夕18時)"

    def test_commented_section_skipped(self, tmp_path):
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "<!--\n"
            "## Disabled (noon)\n"
            "type: llm\n"
            "This should be ignored\n"
            "-->\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert jobs == []

    def test_mixed_active_and_commented(self, tmp_path):
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Active (every hour)\n"
            "type: llm\n"
            "Do work\n\n"
            "<!--\n"
            "## Disabled (noon)\n"
            "type: llm\n"
            "Skip\n"
            "-->\n\n"
            "## Also Active (daily)\n"
            "type: llm\n"
            "More work\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert len(jobs) == 2
        names = [j["name"] for j in jobs]
        assert "Active (every hour)" in names
        assert "Also Active (daily)" in names

    def test_multiple_persons(self, tmp_path):
        persons_dir = tmp_path / "persons"
        for name in ("alice", "bob"):
            d = persons_dir / name
            d.mkdir(parents=True)
            (d / "cron.md").write_text(
                f"# Cron: {name}\n\n## Task ({name})\ntype: llm\nWork\n",
                encoding="utf-8",
            )
        jobs = _parse_cron_jobs(persons_dir, ["alice", "bob"])
        assert len(jobs) == 2
        persons = {j["person"] for j in jobs}
        assert persons == {"alice", "bob"}

    def test_schedule_extracted_from_parentheses(self, tmp_path):
        """Schedule info inside parentheses (both half-width and full-width)."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Task（全角括弧）\n"
            "type: llm\n"
            "Work\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert len(jobs) == 1
        assert jobs[0]["schedule"] == "全角括弧"

    def test_no_schedule_in_title(self, tmp_path):
        """Job title without parentheses -> empty schedule."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "# Cron: alice\n\n"
            "## Simple Task\n"
            "type: llm\n"
            "Work\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice"])
        assert len(jobs) == 1
        assert jobs[0]["schedule"] == ""

    def test_person_without_cron_skipped(self, tmp_path):
        """Person directory exists but has no cron.md."""
        persons_dir = tmp_path / "persons"
        (persons_dir / "alice").mkdir(parents=True)
        bob_dir = persons_dir / "bob"
        bob_dir.mkdir(parents=True)
        (bob_dir / "cron.md").write_text(
            "# Cron: bob\n\n## Task (hourly)\ntype: llm\nWork\n",
            encoding="utf-8",
        )
        jobs = _parse_cron_jobs(persons_dir, ["alice", "bob"])
        assert len(jobs) == 1
        assert jobs[0]["person"] == "bob"
