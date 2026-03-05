"""Unit tests for ConfigReloadManager."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI


def _make_app_with_state(**state_attrs) -> FastAPI:
    app = FastAPI()
    for k, v in state_attrs.items():
        setattr(app.state, k, v)
    return app


class TestConfigReloadManager:
    """Tests for ConfigReloadManager core methods."""

    def _make_manager(self, **state_attrs):
        from server.reload_manager import ConfigReloadManager
        app = _make_app_with_state(**state_attrs)
        return ConfigReloadManager(app)

    @patch("core.config.vault.invalidate_vault_cache")
    @patch("core.config.models.load_config")
    @patch("core.config.models.invalidate_models_json_cache")
    @patch("core.config.models.invalidate_cache")
    async def test_reload_all_success(
        self, mock_inv_cache, mock_inv_models, mock_load, mock_inv_vault,
    ):
        mock_load.return_value = MagicMock(animas={"a": 1, "b": 2})
        mock_slack_mgr = AsyncMock()
        mock_slack_mgr.reload.return_value = {"status": "ok", "added": [], "removed": []}
        mock_supervisor = AsyncMock()

        mgr = self._make_manager(
            slack_socket_manager=mock_slack_mgr,
            supervisor=mock_supervisor,
        )
        result = await mgr.reload_all()

        assert result["config"]["status"] == "ok"
        assert result["config"]["animas_count"] == 2
        assert result["credentials"]["status"] == "ok"
        assert result["slack"]["status"] == "ok"
        assert result["animas"]["status"] == "ok"
        mock_inv_cache.assert_called_once()
        mock_inv_models.assert_called_once()
        mock_inv_vault.assert_called_once()

    @patch("core.config.models.load_config")
    @patch("core.config.models.invalidate_models_json_cache")
    @patch("core.config.models.invalidate_cache")
    async def test_reload_config_cache_error(
        self, mock_inv_cache, mock_inv_models, mock_load,
    ):
        mock_load.side_effect = ValueError("bad config")
        mgr = self._make_manager()
        result = await mgr.reload_all()
        assert result["config"]["status"] == "error"
        assert "bad config" in result["config"]["error"]

    async def test_reload_slack_no_manager(self):
        mgr = self._make_manager()
        result = await mgr.reload_slack()
        assert result["status"] == "skipped"
        assert result["reason"] == "no_manager"

    async def test_reload_slack_delegates_to_manager(self):
        mock_slack_mgr = AsyncMock()
        mock_slack_mgr.reload.return_value = {
            "status": "ok", "added": ["sakura"], "removed": [],
        }
        mgr = self._make_manager(slack_socket_manager=mock_slack_mgr)
        result = await mgr.reload_slack()
        assert result["status"] == "ok"
        assert result["added"] == ["sakura"]
        mock_slack_mgr.reload.assert_awaited_once()

    @patch("core.config.vault.invalidate_vault_cache")
    async def test_reload_credentials_also_reloads_slack(self, mock_inv_vault):
        mock_slack_mgr = AsyncMock()
        mock_slack_mgr.reload.return_value = {"status": "ok"}
        mgr = self._make_manager(slack_socket_manager=mock_slack_mgr)
        result = await mgr.reload_credentials()
        assert result["status"] == "ok"
        assert result["slack"]["status"] == "ok"
        mock_inv_vault.assert_called_once()
        mock_slack_mgr.reload.assert_awaited_once()

    async def test_reload_animas_no_supervisor(self):
        mgr = self._make_manager()
        result = await mgr.reload_animas()
        assert result["status"] == "skipped"
        assert result["reason"] == "no_supervisor"

    async def test_reload_animas_calls_reconcile(self):
        mock_supervisor = AsyncMock()
        mgr = self._make_manager(supervisor=mock_supervisor)
        result = await mgr.reload_animas()
        assert result["status"] == "ok"
        mock_supervisor._reconcile.assert_awaited_once()

    async def test_reload_animas_handles_error(self):
        mock_supervisor = AsyncMock()
        mock_supervisor._reconcile.side_effect = RuntimeError("reconcile failed")
        mgr = self._make_manager(supervisor=mock_supervisor)
        result = await mgr.reload_animas()
        assert result["status"] == "error"
        assert "reconcile failed" in result["error"]


class TestConfigReloadManagerLocking:
    """Tests for asyncio.Lock serialization."""

    async def test_concurrent_reloads_are_serialized(self):
        from server.reload_manager import ConfigReloadManager

        app = _make_app_with_state()
        mgr = ConfigReloadManager(app)

        call_order: list[str] = []
        original_reload_config = mgr._reload_config_cache

        def slow_reload_config():
            call_order.append("start")
            result = original_reload_config()
            call_order.append("end")
            return result

        with patch.object(mgr, "_reload_config_cache", side_effect=slow_reload_config), \
             patch("core.config.models.load_config", return_value=MagicMock(animas={})), \
             patch("core.config.models.invalidate_cache"), \
             patch("core.config.models.invalidate_models_json_cache"), \
             patch("core.config.vault.invalidate_vault_cache"):
            t1 = asyncio.create_task(mgr.reload_all())
            t2 = asyncio.create_task(mgr.reload_all())
            await asyncio.gather(t1, t2)

        assert call_order.count("start") == 2
        assert call_order.count("end") == 2
