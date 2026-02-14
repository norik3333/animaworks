"""Unit tests for setup guard middleware in server/app.py."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_app(setup_complete: bool, tmp_path: Path):
    """Build a test app with the setup guard middleware."""
    from core.config.models import AnimaWorksConfig, invalidate_cache, save_config

    # Write a config file so load_config() works
    config = AnimaWorksConfig(setup_complete=setup_complete)
    config_path = tmp_path / "config.json"
    save_config(config, config_path)
    invalidate_cache()

    persons_dir = tmp_path / "persons"
    persons_dir.mkdir(exist_ok=True)
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir(exist_ok=True)

    with (
        patch("server.app.load_config", return_value=config),
        patch("server.app.ProcessSupervisor") as mock_sup_cls,
    ):
        mock_sup = MagicMock()
        mock_sup_cls.return_value = mock_sup

        from server.app import create_app
        app = create_app(persons_dir, shared_dir)

    return app


class TestSetupGuardNotComplete:
    """When setup_complete=False, the guard should enforce setup-mode routing."""

    async def test_root_redirects_to_setup(self, tmp_path: Path):
        app = _make_app(False, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get("/")

        assert resp.status_code == 307
        assert "/setup/" in resp.headers["location"]

    async def test_setup_api_accessible(self, tmp_path: Path):
        app = _make_app(False, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # detect-locale doesn't need mocking beyond the request
            resp = await client.get("/api/setup/detect-locale")

        assert resp.status_code == 200

    async def test_dashboard_api_blocked(self, tmp_path: Path):
        app = _make_app(False, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")

        assert resp.status_code == 503
        data = resp.json()
        assert "Setup not yet complete" in data["error"]

    async def test_other_paths_redirect_to_setup(self, tmp_path: Path):
        app = _make_app(False, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get("/some/random/path")

        assert resp.status_code == 307
        assert "/setup/" in resp.headers["location"]


class TestSetupGuardComplete:
    """When setup_complete=True, the guard should block setup and allow dashboard."""

    async def test_setup_api_blocked(self, tmp_path: Path):
        app = _make_app(True, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/environment")

        assert resp.status_code == 403
        data = resp.json()
        assert "Setup already completed" in data["error"]

    async def test_setup_page_redirects_to_dashboard(self, tmp_path: Path):
        app = _make_app(True, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get("/setup/")

        assert resp.status_code == 307
        assert resp.headers["location"] == "/"

    async def test_dashboard_api_accessible(self, tmp_path: Path):
        app = _make_app(True, tmp_path)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")

        # Should get 200 (even if empty list)
        assert resp.status_code == 200


class TestSetupGuardTransition:
    """Test that changing setup_complete in app.state switches behaviour."""

    async def test_transition_from_setup_to_complete(self, tmp_path: Path):
        app = _make_app(False, tmp_path)
        transport = ASGITransport(app=app)

        # First: setup API should be accessible
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/detect-locale")
            assert resp.status_code == 200

        # Simulate setup completion
        app.state.setup_complete = True

        # Now: setup API should be blocked
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/detect-locale")
            assert resp.status_code == 403

        # And dashboard API should work
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")
            assert resp.status_code == 200
