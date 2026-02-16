"""E2E tests for activity timeline: pagination, message logs, and type filtering."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── Helpers ──────────────────────────────────────────────


def _create_app(tmp_path: Path, anima_names: list[str] | None = None):
    """Build a real FastAPI app via create_app with mocked externals."""
    animas_dir = tmp_path / "animas"
    animas_dir.mkdir(parents=True, exist_ok=True)
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("server.app.ProcessSupervisor") as mock_sup_cls,
        patch("server.app.load_config") as mock_cfg,
        patch("server.app.WebSocketManager") as mock_ws_cls,
    ):
        cfg = MagicMock()
        cfg.setup_complete = True
        mock_cfg.return_value = cfg
        supervisor = MagicMock()
        supervisor.get_all_status.return_value = {}
        supervisor.get_process_status.return_value = {"status": "stopped", "pid": None}
        supervisor.is_scheduler_running.return_value = False
        supervisor.scheduler = None
        mock_sup_cls.return_value = supervisor
        ws_manager = MagicMock()
        ws_manager.active_connections = []
        mock_ws_cls.return_value = ws_manager
        from server.app import create_app
        app = create_app(animas_dir, shared_dir)
    if anima_names is not None:
        app.state.anima_names = anima_names
    return app


def _setup_anima(animas_dir: Path, name: str) -> Path:
    """Create a minimal anima directory."""
    anima_dir = animas_dir / name
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "identity.md").write_text(f"# {name}", encoding="utf-8")
    return anima_dir


def _write_heartbeat_log(anima_dir: Path, entries: list[dict]) -> None:
    """Write heartbeat log entries."""
    hb_dir = anima_dir / "shortterm" / "heartbeat_history"
    hb_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    log_file = hb_dir / f"{date.today().isoformat()}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_cron_log(anima_dir: Path, entries: list[dict]) -> None:
    """Write cron log entries."""
    cron_dir = anima_dir / "state" / "cron_logs"
    cron_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    log_file = cron_dir / f"{date.today().isoformat()}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_message_log(shared_dir: Path, entries: list[dict]) -> None:
    """Write message log entries."""
    log_dir = shared_dir / "message_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    from datetime import date
    log_file = log_dir / f"{date.today().isoformat()}.jsonl"
    with log_file.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Test 1: Pagination ───────────────────────────────────


class TestActivityPagination:
    """Test pagination parameters (offset, limit, total, has_more)."""

    async def test_default_response_structure(self, tmp_path: Path) -> None:
        app = _create_app(tmp_path, anima_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        assert data["offset"] == 0
        assert data["limit"] == 100
        assert data["has_more"] is False

    async def test_limit_parameter(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        anima_dir = _setup_anima(animas_dir, "alice")
        now = datetime.now(timezone.utc)
        entries = [
            {"timestamp": now.isoformat(), "trigger": "heartbeat", "action": "responded", "summary": f"HB {i}", "duration_ms": 100}
            for i in range(10)
        ]
        _write_heartbeat_log(anima_dir, entries)
        app = _create_app(tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?limit=3")
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["total"] == 10
        assert data["has_more"] is True
        assert data["limit"] == 3

    async def test_offset_parameter(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        anima_dir = _setup_anima(animas_dir, "alice")
        now = datetime.now(timezone.utc)
        entries = [
            {"timestamp": now.isoformat(), "trigger": "heartbeat", "action": "responded", "summary": f"HB {i}", "duration_ms": 100}
            for i in range(5)
        ]
        _write_heartbeat_log(anima_dir, entries)
        app = _create_app(tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?offset=3&limit=10")
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["total"] == 5
        assert data["offset"] == 3
        assert data["has_more"] is False

    async def test_limit_clamped_to_500(self, tmp_path: Path) -> None:
        app = _create_app(tmp_path, anima_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?limit=9999")
        data = resp.json()
        assert data["limit"] == 500


# ── Test 2: Message logs ─────────────────────────────────


class TestActivityMessageLog:
    """Test that inter-anima message logs appear in activity events."""

    async def test_message_events_returned(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        _write_message_log(shared_dir, [
            {"timestamp": now.isoformat(), "from_person": "alice", "to_person": "bob", "type": "message", "summary": "Hello Bob!", "message_id": "msg-1", "thread_id": "t-1"},
        ])
        app = _create_app(tmp_path, anima_names=["alice", "bob"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent")
        data = resp.json()
        msg_events = [e for e in data["events"] if e["type"] == "message"]
        assert len(msg_events) == 1
        evt = msg_events[0]
        assert "alice" in evt["animas"]
        assert "bob" in evt["animas"]
        assert "Hello Bob!" in evt["summary"]
        assert evt["metadata"]["from_person"] == "alice"
        assert evt["metadata"]["to_person"] == "bob"

    async def test_message_events_with_anima_filter(self, tmp_path: Path) -> None:
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        _write_message_log(shared_dir, [
            {"timestamp": now.isoformat(), "from_person": "alice", "to_person": "bob", "type": "message", "summary": "A to B", "message_id": "msg-1", "thread_id": "t-1"},
            {"timestamp": now.isoformat(), "from_person": "charlie", "to_person": "dave", "type": "message", "summary": "C to D", "message_id": "msg-2", "thread_id": "t-2"},
        ])
        app = _create_app(tmp_path, anima_names=["alice", "bob", "charlie", "dave"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?anima=alice")
        data = resp.json()
        msg_events = [e for e in data["events"] if e["type"] == "message"]
        assert len(msg_events) == 1
        assert "A to B" in msg_events[0]["summary"]

    async def test_no_message_log_dir(self, tmp_path: Path) -> None:
        app = _create_app(tmp_path, anima_names=[])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


# ── Test 3: Type filter ──────────────────────────────────


class TestActivityTypeFilter:
    """Test event_type filter parameter."""

    async def test_filter_by_single_type(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        anima_dir = _setup_anima(animas_dir, "alice")
        now = datetime.now(timezone.utc)
        _write_heartbeat_log(anima_dir, [
            {"timestamp": now.isoformat(), "trigger": "heartbeat", "action": "responded", "summary": "HB 1", "duration_ms": 100},
        ])
        _write_cron_log(anima_dir, [
            {"timestamp": now.isoformat(), "task": "daily", "summary": "Cron 1", "duration_ms": 200},
        ])
        _write_message_log(shared_dir, [
            {"timestamp": now.isoformat(), "from_person": "alice", "to_person": "bob", "type": "message", "summary": "msg", "message_id": "m1", "thread_id": "t1"},
        ])
        app = _create_app(tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?event_type=heartbeat")
        data = resp.json()
        assert all(e["type"] == "heartbeat" for e in data["events"])
        assert data["total"] == 1

    async def test_filter_by_multiple_types(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        anima_dir = _setup_anima(animas_dir, "alice")
        now = datetime.now(timezone.utc)
        _write_heartbeat_log(anima_dir, [
            {"timestamp": now.isoformat(), "trigger": "heartbeat", "action": "responded", "summary": "HB", "duration_ms": 100},
        ])
        _write_cron_log(anima_dir, [
            {"timestamp": now.isoformat(), "task": "daily", "summary": "Cron", "duration_ms": 200},
        ])
        _write_message_log(shared_dir, [
            {"timestamp": now.isoformat(), "from_person": "alice", "to_person": "bob", "type": "message", "summary": "msg", "message_id": "m1", "thread_id": "t1"},
        ])
        app = _create_app(tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent?event_type=heartbeat,message")
        data = resp.json()
        types = {e["type"] for e in data["events"]}
        assert types == {"heartbeat", "message"}
        assert data["total"] == 2


# ── Test 4: Mixed events ─────────────────────────────────


class TestActivityMixedEvents:
    """Test that all event types are properly aggregated."""

    async def test_all_event_types_aggregated(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        anima_dir = _setup_anima(animas_dir, "alice")
        now = datetime.now(timezone.utc)
        _write_heartbeat_log(anima_dir, [
            {"timestamp": now.isoformat(), "trigger": "heartbeat", "action": "responded", "summary": "HB", "duration_ms": 100},
        ])
        _write_cron_log(anima_dir, [
            {"timestamp": now.isoformat(), "task": "daily", "summary": "Cron", "duration_ms": 200},
        ])
        _write_message_log(shared_dir, [
            {"timestamp": now.isoformat(), "from_person": "alice", "to_person": "bob", "type": "message", "summary": "msg", "message_id": "m1", "thread_id": "t1"},
        ])
        app = _create_app(tmp_path, anima_names=["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/activity/recent")
        data = resp.json()
        types = {e["type"] for e in data["events"]}
        assert "heartbeat" in types
        assert "cron" in types
        assert "message" in types
