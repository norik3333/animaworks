"""E2E tests for the setup wizard flow.

Tests the complete setup wizard lifecycle including:
- Setup guard middleware (route blocking/allowing)
- Setup API endpoints (environment, locale, templates, validate-key)
- Full wizard flow (fresh config → setup → route switching)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.config import AnimaWorksConfig, invalidate_cache, save_config


# ── Helpers ──────────────────────────────────────────────────


def _write_config(data_dir: Path, *, setup_complete: bool = False, **overrides: Any) -> None:
    """Write a config.json with the given setup_complete flag."""
    invalidate_cache()
    config = AnimaWorksConfig(setup_complete=setup_complete, **overrides)
    save_config(config, data_dir / "config.json")
    invalidate_cache()


def _create_app(data_dir: Path) -> Any:
    """Create a FastAPI app pointing at the test data_dir."""
    from server.app import create_app

    persons_dir = data_dir / "persons"
    shared_dir = data_dir / "shared"
    return create_app(persons_dir, shared_dir)


@pytest.fixture
def setup_app(data_dir: Path):
    """Create a fresh app in setup mode (setup_complete=False)."""
    _write_config(data_dir, setup_complete=False)
    return _create_app(data_dir)


@pytest.fixture
def completed_app(data_dir: Path):
    """Create an app where setup is already complete."""
    _write_config(data_dir, setup_complete=True)
    return _create_app(data_dir)


# ── 1. Setup Guard Tests ────────────────────────────────────


class TestSetupGuard:
    """Test the setup guard middleware controls route access."""

    @pytest.mark.asyncio
    async def test_setup_routes_accessible_during_setup(self, setup_app):
        """Setup API routes are accessible when setup_complete=False."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_non_setup_api_blocked_during_setup(self, setup_app):
        """Non-setup API routes return 503 during setup."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/persons")
            assert resp.status_code == 503
            body = resp.json()
            assert "Setup not yet complete" in body["error"]

    @pytest.mark.asyncio
    async def test_root_redirects_to_setup_during_setup(self, setup_app):
        """Root / redirects to /setup/ when setup is not complete."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 307
            assert "/setup/" in resp.headers["location"]

    @pytest.mark.asyncio
    async def test_setup_api_blocked_after_completion(self, completed_app):
        """Setup API routes return 403 after setup is complete."""
        transport = ASGITransport(app=completed_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 403
            body = resp.json()
            assert "Setup already completed" in body["error"]

    @pytest.mark.asyncio
    async def test_setup_page_redirects_after_completion(self, completed_app):
        """Accessing /setup/ after completion redirects to /."""
        transport = ASGITransport(app=completed_app)
        async with AsyncClient(
            transport=transport, base_url="http://test", follow_redirects=False
        ) as client:
            resp = await client.get("/setup/")
            assert resp.status_code == 307
            assert resp.headers["location"] == "/"

    @pytest.mark.asyncio
    async def test_multiple_api_routes_blocked_during_setup(self, setup_app):
        """Various non-setup API routes all return 503."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ["/api/persons", "/api/system/health", "/api/sessions"]:
                resp = await client.get(path)
                assert resp.status_code == 503, f"{path} should return 503 during setup"


# ── 2. Setup Flow Integration ───────────────────────────────


class TestSetupEndpoints:
    """Test individual setup API endpoints."""

    @pytest.mark.asyncio
    async def test_get_environment(self, setup_app):
        """GET /api/setup/environment returns correct structure."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 200
            body = resp.json()

            assert "claude_code_available" in body
            assert isinstance(body["claude_code_available"], bool)
            assert "locale" in body
            assert "providers" in body
            assert isinstance(body["providers"], list)
            assert len(body["providers"]) > 0
            assert "available_locales" in body
            assert "ja" in body["available_locales"]
            assert "en" in body["available_locales"]

    @pytest.mark.asyncio
    async def test_get_environment_providers_structure(self, setup_app):
        """Providers in environment response have correct fields."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/environment")
            body = resp.json()

            for provider in body["providers"]:
                assert "id" in provider
                assert "name" in provider
                assert "models" in provider
                assert isinstance(provider["models"], list)
                # env_key can be None (e.g. for Ollama)
                assert "env_key" in provider

    @pytest.mark.asyncio
    async def test_detect_locale_japanese(self, setup_app):
        """GET /api/setup/detect-locale detects Japanese from Accept-Language."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["detected"] == "ja"
            assert "available" in body

    @pytest.mark.asyncio
    async def test_detect_locale_english(self, setup_app):
        """GET /api/setup/detect-locale detects English from Accept-Language."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["detected"] == "en"

    @pytest.mark.asyncio
    async def test_detect_locale_fallback(self, setup_app):
        """GET /api/setup/detect-locale falls back to 'ja' for unknown locales."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"Accept-Language": "fr-FR,de;q=0.9"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["detected"] == "ja"

    @pytest.mark.asyncio
    async def test_detect_locale_no_header(self, setup_app):
        """GET /api/setup/detect-locale defaults to 'ja' without Accept-Language."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/detect-locale")
            assert resp.status_code == 200
            body = resp.json()
            assert body["detected"] == "ja"

    @pytest.mark.asyncio
    async def test_list_templates(self, setup_app):
        """GET /api/setup/templates returns available templates."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/templates")
            assert resp.status_code == 200
            body = resp.json()
            assert "templates" in body
            assert isinstance(body["templates"], list)

    @pytest.mark.asyncio
    async def test_validate_key_ollama(self, setup_app):
        """POST /api/setup/validate-key for Ollama always returns valid."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/validate-key",
                json={"provider": "ollama", "api_key": ""},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_key_unknown_provider(self, setup_app):
        """POST /api/setup/validate-key for unknown provider returns invalid."""
        transport = ASGITransport(app=setup_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/validate-key",
                json={"provider": "nonexistent", "api_key": "sk-test"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["valid"] is False
            assert "Unknown provider" in body["message"]

    @pytest.mark.asyncio
    async def test_validate_key_anthropic_mocked(self, setup_app):
        """POST /api/setup/validate-key for Anthropic with mocked HTTP call."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            transport = ASGITransport(app=setup_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "anthropic", "api_key": "sk-ant-test123"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_key_anthropic_invalid(self, setup_app):
        """POST /api/setup/validate-key for Anthropic with invalid key."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 401

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            transport = ASGITransport(app=setup_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "anthropic", "api_key": "invalid-key"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["valid"] is False

    @pytest.mark.asyncio
    async def test_validate_key_openai_mocked(self, setup_app):
        """POST /api/setup/validate-key for OpenAI with mocked HTTP call."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            transport = ASGITransport(app=setup_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "openai", "api_key": "sk-test"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_key_google_mocked(self, setup_app):
        """POST /api/setup/validate-key for Google with mocked HTTP call."""
        mock_resp = AsyncMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            transport = ASGITransport(app=setup_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "google", "api_key": "AIza-test"},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["valid"] is True


# ── 3. Setup Completion & Full Wizard Flow ──────────────────


class TestSetupComplete:
    """Test POST /api/setup/complete and the full wizard flow."""

    @pytest.mark.asyncio
    async def test_complete_setup_minimal(self, data_dir: Path):
        """Complete setup with minimal payload (no person)."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/complete",
                json={"locale": "en"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"

        # Verify config was updated
        invalidate_cache()
        config_raw = json.loads((data_dir / "config.json").read_text("utf-8"))
        assert config_raw["setup_complete"] is True
        assert config_raw["locale"] == "en"

    @pytest.mark.asyncio
    async def test_complete_setup_with_credentials(self, data_dir: Path):
        """Complete setup saves credentials to config."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/complete",
                json={
                    "locale": "ja",
                    "credentials": {
                        "anthropic": {"api_key": "sk-ant-test"},
                        "openai": {"api_key": "sk-oai-test"},
                    },
                },
            )
            assert resp.status_code == 200

        invalidate_cache()
        config_raw = json.loads((data_dir / "config.json").read_text("utf-8"))
        assert config_raw["credentials"]["anthropic"]["api_key"] == "sk-ant-test"
        assert config_raw["credentials"]["openai"]["api_key"] == "sk-oai-test"

    @pytest.mark.asyncio
    async def test_complete_setup_creates_blank_person(self, data_dir: Path):
        """Complete setup with person creates a blank person directory."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/complete",
                json={
                    "locale": "ja",
                    "person": {"name": "hinata"},
                },
            )
            assert resp.status_code == 200

        # Verify person directory was created
        person_dir = data_dir / "persons" / "hinata"
        assert person_dir.exists()
        assert (person_dir / "state").is_dir()

        # Verify person was added to config
        invalidate_cache()
        config_raw = json.loads((data_dir / "config.json").read_text("utf-8"))
        assert "hinata" in config_raw["persons"]

    @pytest.mark.asyncio
    async def test_complete_setup_with_custom_identity(self, data_dir: Path):
        """Complete setup writes custom identity.md when provided."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        identity_text = "# Sakura\nA cheerful AI assistant."
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/complete",
                json={
                    "locale": "ja",
                    "person": {
                        "name": "sakura",
                        "identity_md": identity_text,
                    },
                },
            )
            assert resp.status_code == 200

        identity_path = data_dir / "persons" / "sakura" / "identity.md"
        assert identity_path.exists()
        assert identity_path.read_text("utf-8") == identity_text

    @pytest.mark.asyncio
    async def test_route_switching_after_completion(self, data_dir: Path):
        """After setup completion, middleware switches: setup blocked, API open."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Before completion: setup accessible, API blocked
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 200

            resp = await client.get("/api/persons")
            assert resp.status_code == 503

            # Complete setup
            resp = await client.post(
                "/api/setup/complete",
                json={"locale": "ja"},
            )
            assert resp.status_code == 200

            # After completion: setup blocked, API accessible
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 403

            # /api/persons should no longer return 503
            resp = await client.get("/api/persons")
            assert resp.status_code != 503

    @pytest.mark.asyncio
    async def test_full_wizard_flow(self, data_dir: Path):
        """End-to-end flow: fresh config → detect → configure → complete → verify."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Step 1: Root redirects to setup
            resp = await client.get("/", follow_redirects=False)
            assert resp.status_code == 307
            assert "/setup/" in resp.headers["location"]

            # Step 2: Detect environment
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 200
            env_data = resp.json()
            assert "providers" in env_data

            # Step 3: Detect locale
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"Accept-Language": "ja,en;q=0.9"},
            )
            assert resp.status_code == 200
            assert resp.json()["detected"] == "ja"

            # Step 4: List templates
            resp = await client.get("/api/setup/templates")
            assert resp.status_code == 200
            assert "templates" in resp.json()

            # Step 5: Validate key (Ollama — no external call)
            resp = await client.post(
                "/api/setup/validate-key",
                json={"provider": "ollama", "api_key": ""},
            )
            assert resp.status_code == 200
            assert resp.json()["valid"] is True

            # Step 6: Complete setup with person creation
            resp = await client.post(
                "/api/setup/complete",
                json={
                    "locale": "ja",
                    "credentials": {
                        "anthropic": {"api_key": "sk-ant-test"},
                    },
                    "person": {"name": "aoi"},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Step 7: Verify setup_complete in config
            invalidate_cache()
            config_raw = json.loads((data_dir / "config.json").read_text("utf-8"))
            assert config_raw["setup_complete"] is True

            # Step 8: Verify person was created
            assert (data_dir / "persons" / "aoi").is_dir()
            assert "aoi" in config_raw["persons"]

            # Step 9: Verify route switching
            resp = await client.get("/api/setup/environment")
            assert resp.status_code == 403

            resp = await client.get("/api/persons")
            assert resp.status_code != 503

    @pytest.mark.asyncio
    async def test_duplicate_person_handled_gracefully(self, data_dir: Path, make_person):
        """Completing setup with an existing person name doesn't crash."""
        make_person("existing")
        _write_config(data_dir, setup_complete=False)
        # Ensure the person dir survives the config rewrite
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/complete",
                json={
                    "locale": "ja",
                    "person": {"name": "existing"},
                },
            )
            # Should succeed (logs warning but does not fail)
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_setup_complete_idempotent_config(self, data_dir: Path):
        """Calling complete twice (via direct config) keeps setup_complete=True."""
        _write_config(data_dir, setup_complete=False)
        app = _create_app(data_dir)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First completion
            resp = await client.post(
                "/api/setup/complete",
                json={"locale": "ja"},
            )
            assert resp.status_code == 200

            # Second call should be blocked by middleware (403)
            resp = await client.post(
                "/api/setup/complete",
                json={"locale": "en"},
            )
            assert resp.status_code == 403
