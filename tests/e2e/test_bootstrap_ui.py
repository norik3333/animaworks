"""E2E tests for bootstrap UI feature — person list and start endpoints.

Tests the API integration points that drive the frontend bootstrap UI:
1. GET /api/persons returns bootstrapping flag per person
2. POST /api/persons/{name}/start triggers person startup
3. Start endpoint rejects already-running persons
4. Bootstrapping person transitions to idle after completion
5. Multiple persons can have independent states simultaneously
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── Helpers ──────────────────────────────────────────────────


def _create_app(
    tmp_path: Path,
    person_names: list[str] | None = None,
    supervisor: MagicMock | None = None,
) -> "FastAPI":  # noqa: F821
    """Build a real FastAPI app via create_app with mocked externals.

    Args:
        tmp_path: Temporary directory for person/shared data.
        person_names: Override discovered person names.
        supervisor: Optional pre-configured mock supervisor. When not
            supplied a default mock is created.
    """
    persons_dir = tmp_path / "persons"
    persons_dir.mkdir(parents=True, exist_ok=True)
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

        sup = supervisor or MagicMock()
        if supervisor is None:
            sup.get_all_status.return_value = {}
            sup.get_process_status.return_value = {
                "status": "stopped",
                "pid": None,
                "bootstrapping": False,
            }
        mock_sup_cls.return_value = sup

        ws_manager = MagicMock()
        ws_manager.active_connections = []
        mock_ws_cls.return_value = ws_manager

        from server.app import create_app

        app = create_app(persons_dir, shared_dir)

    if person_names is not None:
        app.state.person_names = person_names

    return app


def _create_person_on_disk(persons_dir: Path, name: str) -> Path:
    """Create a minimal person directory on disk."""
    person_dir = persons_dir / name
    person_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("episodes", "knowledge", "procedures", "state", "shortterm"):
        (person_dir / subdir).mkdir(exist_ok=True)
    (person_dir / "identity.md").write_text(
        f"# {name}\nTest person.", encoding="utf-8",
    )
    (person_dir / "injection.md").write_text("", encoding="utf-8")
    (person_dir / "permissions.md").write_text("", encoding="utf-8")
    return person_dir


def _make_supervisor_mock(
    statuses: dict[str, dict] | None = None,
) -> MagicMock:
    """Create a mock supervisor with configurable per-person status.

    Args:
        statuses: Mapping from person name to the dict returned by
            ``get_process_status(name)``.  Names not in this mapping
            return a default ``not_found`` status.
    """
    statuses = statuses or {}
    sup = MagicMock()
    sup.get_all_status.return_value = statuses

    def _get_process_status(name: str) -> dict:
        return statuses.get(name, {"status": "not_found", "bootstrapping": False})

    sup.get_process_status = MagicMock(side_effect=_get_process_status)
    sup.start_person = AsyncMock()
    return sup


# ── Tests ────────────────────────────────────────────────────


class TestPersonListBootstrapIntegration:
    """Test GET /api/persons returns correct bootstrap status."""

    async def test_person_list_shows_bootstrapping_status(
        self, tmp_path: Path,
    ) -> None:
        """When supervisor reports a person as bootstrapping, the
        GET /api/persons response includes ``bootstrapping: True``."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "bootstrapping",
                    "pid": 12345,
                    "uptime_sec": 5.0,
                    "bootstrapping": True,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        alice = data[0]
        assert alice["name"] == "alice"
        assert alice["bootstrapping"] is True
        assert alice["status"] == "bootstrapping"

    async def test_person_start_triggers_bootstrap(
        self, tmp_path: Path,
    ) -> None:
        """POST /api/persons/{name}/start calls supervisor.start_person
        and returns ``{status: started}``."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "stopped",
                    "pid": None,
                    "uptime_sec": None,
                    "bootstrapping": False,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/persons/alice/start")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert body["name"] == "alice"

        # Verify supervisor.start_person was called exactly once
        supervisor.start_person.assert_awaited_once_with("alice")

    async def test_start_endpoint_rejects_running_person(
        self, tmp_path: Path,
    ) -> None:
        """When a person is already running, POST /start returns
        ``{status: already_running}`` without calling start_person."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "running",
                    "pid": 99999,
                    "uptime_sec": 120.0,
                    "bootstrapping": False,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/persons/alice/start")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "already_running"
        assert body["current_status"] == "running"

        # start_person should NOT have been called
        supervisor.start_person.assert_not_awaited()

    async def test_bootstrapping_person_transitions_to_idle(
        self, tmp_path: Path,
    ) -> None:
        """After bootstrap completes, the person status should reflect
        'running' (idle) rather than 'bootstrapping'.

        This simulates two successive GET /api/persons calls: the first
        during bootstrap, the second after bootstrap completes.
        """
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        # Phase 1: bootstrapping
        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "bootstrapping",
                    "pid": 12345,
                    "uptime_sec": 3.0,
                    "bootstrapping": True,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.get("/api/persons")

        data1 = resp1.json()
        assert data1[0]["bootstrapping"] is True
        assert data1[0]["status"] == "bootstrapping"

        # Phase 2: bootstrap complete — update supervisor mock to return
        # running status.  Since the route calls supervisor.get_process_status
        # on each request, changing the mock is equivalent to the bootstrap
        # finishing between the two requests.
        app.state.supervisor.get_process_status = MagicMock(
            return_value={
                "status": "running",
                "pid": 12345,
                "uptime_sec": 30.0,
                "bootstrapping": False,
            },
        )

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp2 = await client.get("/api/persons")

        data2 = resp2.json()
        assert data2[0]["bootstrapping"] is False
        assert data2[0]["status"] == "running"

    async def test_multiple_persons_independent_states(
        self, tmp_path: Path,
    ) -> None:
        """Two persons can have different states simultaneously — one
        sleeping (stopped), one bootstrapping."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")
        _create_person_on_disk(persons_dir, "bob")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "stopped",
                    "pid": None,
                    "uptime_sec": None,
                    "bootstrapping": False,
                },
                "bob": {
                    "status": "bootstrapping",
                    "pid": 54321,
                    "uptime_sec": 2.0,
                    "bootstrapping": True,
                },
            },
        )

        app = _create_app(
            tmp_path, person_names=["alice", "bob"], supervisor=supervisor,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        persons = {p["name"]: p for p in data}

        # Alice is sleeping (stopped)
        assert persons["alice"]["status"] == "stopped"
        assert persons["alice"]["bootstrapping"] is False

        # Bob is bootstrapping
        assert persons["bob"]["status"] == "bootstrapping"
        assert persons["bob"]["bootstrapping"] is True

    async def test_start_unknown_person_returns_404(
        self, tmp_path: Path,
    ) -> None:
        """POST /api/persons/{name}/start for a name not in person_names
        returns 404."""
        supervisor = _make_supervisor_mock()
        app = _create_app(tmp_path, person_names=[], supervisor=supervisor)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/persons/nobody/start")

        assert resp.status_code == 404

    async def test_start_stopped_person_is_accepted(
        self, tmp_path: Path,
    ) -> None:
        """POST /start with status 'not_found' (never started) is accepted."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "not_found",
                    "bootstrapping": False,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/persons/alice/start")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        supervisor.start_person.assert_awaited_once_with("alice")

    async def test_person_list_non_bootstrapping_person(
        self, tmp_path: Path,
    ) -> None:
        """A running person that is NOT bootstrapping has
        ``bootstrapping: False``."""
        persons_dir = tmp_path / "persons"
        _create_person_on_disk(persons_dir, "alice")

        supervisor = _make_supervisor_mock(
            statuses={
                "alice": {
                    "status": "running",
                    "pid": 11111,
                    "uptime_sec": 600.0,
                    "bootstrapping": False,
                },
            },
        )

        app = _create_app(tmp_path, person_names=["alice"], supervisor=supervisor)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")

        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["bootstrapping"] is False
        assert data[0]["status"] == "running"
