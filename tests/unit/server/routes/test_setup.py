"""Unit tests for server/routes/setup.py — Setup wizard API endpoints."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from server.routes.setup import (
    AVAILABLE_LOCALES,
    AVAILABLE_PROVIDERS,
    _parse_accept_language,
    create_setup_router,
)


# ── Helper to build a minimal FastAPI app with setup router ──


def _make_test_app(setup_complete: bool = False):
    from fastapi import FastAPI

    app = FastAPI()
    app.state.setup_complete = setup_complete
    router = create_setup_router()
    app.include_router(router)
    return app


# ── _parse_accept_language ───────────────────────────────


class TestParseAcceptLanguage:
    def test_empty_returns_ja(self):
        assert _parse_accept_language("") == "ja"

    def test_ja_header(self):
        assert _parse_accept_language("ja") == "ja"

    def test_en_header(self):
        assert _parse_accept_language("en") == "en"

    def test_en_us_normalizes_to_en(self):
        assert _parse_accept_language("en-US") == "en"

    def test_weighted_prefers_higher_quality(self):
        assert _parse_accept_language("en;q=0.8,ja;q=0.9") == "ja"

    def test_weighted_en_first(self):
        assert _parse_accept_language("en;q=0.9,ja;q=0.8") == "en"

    def test_no_quality_defaults_to_1(self):
        # "ja" without q= has quality 1.0, "en;q=0.5" has 0.5
        assert _parse_accept_language("ja,en;q=0.5") == "ja"

    def test_unknown_locale_falls_back_to_ja(self):
        assert _parse_accept_language("fr,de") == "ja"

    def test_mixed_known_unknown(self):
        assert _parse_accept_language("fr;q=1.0,en;q=0.8") == "en"

    def test_complex_header(self):
        header = "ja;q=0.9,en-US;q=0.8,en;q=0.7,fr;q=0.5"
        assert _parse_accept_language(header) == "ja"

    def test_invalid_quality_ignored(self):
        # "en;q=notanumber" → q=0.0, "ja" → q=1.0
        assert _parse_accept_language("en;q=notanumber,ja") == "ja"


# ── GET /api/setup/environment ───────────────────────────


class TestGetEnvironment:
    async def test_returns_environment_info(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("shutil.which", return_value="/usr/bin/claude"),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/setup/environment")

        assert resp.status_code == 200
        data = resp.json()
        assert data["claude_code_available"] is True
        assert data["locale"] == "ja"
        assert data["providers"] == AVAILABLE_PROVIDERS
        assert data["available_locales"] == AVAILABLE_LOCALES

    async def test_claude_not_available(self):
        mock_config = MagicMock()
        mock_config.locale = "en"

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("shutil.which", return_value=None),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/setup/environment")

        data = resp.json()
        assert data["claude_code_available"] is False
        assert data["locale"] == "en"


# ── GET /api/setup/detect-locale ─────────────────────────


class TestDetectLocale:
    async def test_ja_header(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"accept-language": "ja"},
            )

        data = resp.json()
        assert data["detected"] == "ja"
        assert data["available"] == AVAILABLE_LOCALES

    async def test_en_us_header(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/setup/detect-locale",
                headers={"accept-language": "en-US,en;q=0.9"},
            )

        data = resp.json()
        assert data["detected"] == "en"

    async def test_no_header_defaults_ja(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/setup/detect-locale")

        data = resp.json()
        assert data["detected"] == "ja"


# ── POST /api/setup/validate-key ─────────────────────────


class TestValidateKey:
    async def test_anthropic_valid(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("server.routes.setup._validate_anthropic_key", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = {"valid": True, "message": "API key is valid"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "anthropic", "api_key": "sk-test"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    async def test_anthropic_invalid(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("server.routes.setup._validate_anthropic_key", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = {"valid": False, "message": "Invalid API key"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "anthropic", "api_key": "bad-key"},
                )

        data = resp.json()
        assert data["valid"] is False

    async def test_openai_validation(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("server.routes.setup._validate_openai_key", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = {"valid": True, "message": "API key is valid"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "openai", "api_key": "sk-openai"},
                )

        data = resp.json()
        assert data["valid"] is True

    async def test_google_validation(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("server.routes.setup._validate_google_key", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = {"valid": True, "message": "API key is valid"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/validate-key",
                    json={"provider": "google", "api_key": "google-key"},
                )

        data = resp.json()
        assert data["valid"] is True

    async def test_ollama_no_key_needed(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/validate-key",
                json={"provider": "ollama", "api_key": ""},
            )

        data = resp.json()
        assert data["valid"] is True
        assert "does not require" in data["message"]

    async def test_unknown_provider(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/setup/validate-key",
                json={"provider": "unknown_provider", "api_key": "key"},
            )

        data = resp.json()
        assert data["valid"] is False
        assert "Unknown provider" in data["message"]


# ── GET /api/setup/templates ─────────────────────────────


class TestListTemplates:
    async def test_returns_templates(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("core.person_factory.list_person_templates", return_value=["assistant", "researcher"]):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/setup/templates")

        assert resp.status_code == 200
        data = resp.json()
        assert data["templates"] == ["assistant", "researcher"]

    async def test_empty_templates(self):
        app = _make_test_app()
        transport = ASGITransport(app=app)

        with patch("core.person_factory.list_person_templates", return_value=[]):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/setup/templates")

        data = resp.json()
        assert data["templates"] == []


# ── POST /api/setup/complete ─────────────────────────────


class TestCompleteSetup:
    async def test_basic_complete(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config") as mock_save,
            patch("core.config.invalidate_cache") as mock_invalidate,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={"locale": "en", "credentials": {}},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert mock_config.locale == "en"
        assert mock_config.setup_complete is True
        mock_save.assert_called_once_with(mock_config)
        mock_invalidate.assert_called_once()

    async def test_complete_with_credentials(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={
                        "locale": "ja",
                        "credentials": {
                            "anthropic": {"api_key": "sk-test-key"},
                        },
                    },
                )

        assert resp.status_code == 200
        assert "anthropic" in mock_config.credentials

    async def test_complete_with_template_person(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
            patch("core.paths.get_persons_dir", return_value=Path("/tmp/test/persons")),
            patch("core.person_factory.create_from_template") as mock_create_tmpl,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={
                        "locale": "ja",
                        "credentials": {},
                        "person": {"name": "alice", "template": "assistant"},
                    },
                )

        assert resp.status_code == 200
        mock_create_tmpl.assert_called_once_with(
            Path("/tmp/test/persons"),
            "assistant",
            person_name="alice",
        )

    async def test_complete_with_blank_person(self, tmp_path: Path):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
            patch("core.paths.get_persons_dir", return_value=tmp_path / "persons"),
            patch("core.person_factory.create_blank", return_value=person_dir),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={
                        "locale": "ja",
                        "credentials": {},
                        "person": {
                            "name": "alice",
                            "identity_md": "# Alice\nA helpful assistant.",
                        },
                    },
                )

        assert resp.status_code == 200
        # identity.md should have been written
        identity_path = person_dir / "identity.md"
        assert identity_path.exists()
        assert identity_path.read_text(encoding="utf-8") == "# Alice\nA helpful assistant."

    async def test_complete_updates_app_state(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app(setup_complete=False)
        assert app.state.setup_complete is False

        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={"locale": "ja", "credentials": {}},
                )

        assert resp.status_code == 200
        assert app.state.setup_complete is True

    async def test_complete_person_already_exists(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
            patch("core.paths.get_persons_dir", return_value=Path("/tmp/test/persons")),
            patch("core.person_factory.create_from_template", side_effect=FileExistsError("already exists")),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={
                        "locale": "ja",
                        "credentials": {},
                        "person": {"name": "alice", "template": "assistant"},
                    },
                )

        # Should succeed despite FileExistsError (person creation is skipped)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    async def test_complete_person_creation_fails(self):
        mock_config = MagicMock()
        mock_config.locale = "ja"
        mock_config.credentials = {}
        mock_config.persons = {}

        app = _make_test_app()
        transport = ASGITransport(app=app)

        with (
            patch("core.config.load_config", return_value=mock_config),
            patch("core.config.save_config"),
            patch("core.config.invalidate_cache"),
            patch("core.paths.get_persons_dir", return_value=Path("/tmp/test/persons")),
            patch("core.person_factory.create_from_template", side_effect=RuntimeError("disk error")),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/setup/complete",
                    json={
                        "locale": "ja",
                        "credentials": {},
                        "person": {"name": "alice", "template": "assistant"},
                    },
                )

        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
