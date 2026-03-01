"""Tests for session TTL and password-change session revocation (AUTH-1).

Covers:
- validate_session() TTL expiry check
- session_ttl_days=None (unlimited) bypasses expiry
- session_ttl_days default=7
- Expired sessions are auto-revoked from auth.json
- change_password revokes all existing sessions
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from core.auth.manager import (
    create_session,
    hash_password,
    load_auth,
    save_auth,
    validate_session,
)
from core.auth.models import AuthConfig, AuthUser, Session
from core.config.models import ServerConfig

_LOAD_CONFIG_PATH = "core.config.models.load_config"


# ── validate_session TTL tests ───────────────────────────────


class TestValidateSessionTTL:
    """validate_session() must reject expired sessions based on TTL."""

    def test_valid_session_within_ttl(self, data_dir: Path):
        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(username="admin", password_hash="hash"),
        )
        token = create_session(config, "admin")
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=7)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session(token)
        assert session is not None
        assert session.username == "admin"

    def test_expired_session_rejected(self, data_dir: Path):
        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(username="admin", password_hash="hash"),
        )
        config.sessions["old-token"] = Session(
            username="admin",
            created_at=datetime.now(timezone.utc) - timedelta(days=8),
        )
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=7)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session("old-token")
        assert session is None

        reloaded = load_auth()
        assert "old-token" not in reloaded.sessions

    def test_unlimited_ttl_allows_old_session(self, data_dir: Path):
        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(username="admin", password_hash="hash"),
        )
        config.sessions["ancient-token"] = Session(
            username="admin",
            created_at=datetime.now(timezone.utc) - timedelta(days=365),
        )
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=None)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session("ancient-token")
        assert session is not None
        assert session.username == "admin"

    def test_none_token_returns_none(self, data_dir: Path):
        assert validate_session(None) is None

    def test_unknown_token_returns_none(self, data_dir: Path):
        config = AuthConfig(auth_mode="password")
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=7)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session("nonexistent-token")
        assert session is None

    def test_session_exactly_at_ttl_boundary(self, data_dir: Path):
        """Session created exactly TTL days ago should be expired."""
        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(username="admin", password_hash="hash"),
        )
        config.sessions["boundary-token"] = Session(
            username="admin",
            created_at=datetime.now(timezone.utc) - timedelta(days=7, seconds=1),
        )
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=7)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session("boundary-token")
        assert session is None

    def test_naive_datetime_treated_as_utc(self, data_dir: Path):
        """Sessions with naive datetime (no tzinfo) should work correctly."""
        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(username="admin", password_hash="hash"),
        )
        config.sessions["naive-token"] = Session(
            username="admin",
            created_at=datetime.now() - timedelta(days=8),
        )
        save_auth(config)

        server_cfg = ServerConfig(session_ttl_days=7)
        with patch(_LOAD_CONFIG_PATH) as mock_cfg:
            mock_cfg.return_value.server = server_cfg
            session = validate_session("naive-token")
        assert session is None


# ── ServerConfig default ─────────────────────────────────────


class TestServerConfigDefault:
    def test_default_session_ttl_days(self):
        cfg = ServerConfig()
        assert cfg.session_ttl_days == 7

    def test_session_ttl_days_nullable(self):
        cfg = ServerConfig(session_ttl_days=None)
        assert cfg.session_ttl_days is None

    def test_session_ttl_days_custom(self):
        cfg = ServerConfig(session_ttl_days=30)
        assert cfg.session_ttl_days == 30


# ── change_password session revocation ───────────────────────


class TestChangePasswordRevokesSession:
    """change_password endpoint must revoke all sessions for the user."""

    def _create_test_app(self, data_dir: Path):
        import json
        from unittest.mock import MagicMock
        from server.app import create_app

        animas_dir = data_dir / "animas"
        animas_dir.mkdir(exist_ok=True)
        shared_dir = data_dir / "shared"
        shared_dir.mkdir(exist_ok=True)

        config_path = data_dir / "config.json"
        if config_path.exists():
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            config_data = {}
        config_data["setup_complete"] = True
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        from core.config import invalidate_cache
        invalidate_cache()

        with patch("core.paths.get_data_dir", return_value=data_dir), \
             patch("server.app.ProcessSupervisor"), \
             patch("server.app.WebSocketManager"):
            app = create_app(animas_dir, shared_dir)
        return app

    def test_change_password_revokes_existing_sessions(self, data_dir: Path):
        from fastapi.testclient import TestClient

        config = AuthConfig(
            auth_mode="password",
            owner=AuthUser(
                username="admin",
                password_hash=hash_password("oldpw"),
                role="owner",
            ),
        )
        token1 = create_session(config, "admin")
        token2 = create_session(config, "admin")
        save_auth(config)

        app = self._create_test_app(data_dir)
        client = TestClient(app)
        client.post("/api/auth/login", json={
            "username": "admin",
            "password": "oldpw",
        })

        resp = client.put("/api/users/me/password", json={
            "current_password": "oldpw",
            "new_password": "newpw123",
        })
        assert resp.status_code == 200

        reloaded = load_auth()
        assert token1 not in reloaded.sessions
        assert token2 not in reloaded.sessions

    def test_change_password_local_trust_upgrade_creates_new_session(
        self, data_dir: Path,
    ):
        from fastapi.testclient import TestClient

        config = AuthConfig(
            auth_mode="local_trust",
            trust_localhost=True,
            owner=AuthUser(username="admin", role="owner"),
        )
        save_auth(config)

        app = self._create_test_app(data_dir)
        client = TestClient(app)

        resp = client.put("/api/users/me/password", json={
            "current_password": "",
            "new_password": "newpw123",
        })
        assert resp.status_code == 200

        reloaded = load_auth()
        assert reloaded.auth_mode == "password"
        assert len(reloaded.sessions) == 1

        session = next(iter(reloaded.sessions.values()))
        assert session.username == "admin"
