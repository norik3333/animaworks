"""Unit tests for SlackSocketModeManager.reload() — diff-based handler management."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSlackSocketReload:
    """Tests for SlackSocketModeManager.reload()."""

    def _make_manager(self):
        from server.slack_socket import SlackSocketModeManager
        return SlackSocketModeManager()

    @patch("server.slack_socket.load_config")
    async def test_reload_returns_disabled_when_slack_off(self, mock_config):
        slack_cfg = MagicMock(enabled=False, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )
        mgr = self._make_manager()
        result = await mgr.reload()
        assert result["status"] == "disabled"

    @patch("server.slack_socket.load_config")
    async def test_reload_stops_all_when_slack_disabled(self, mock_config):
        slack_cfg = MagicMock(enabled=False, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )
        mgr = self._make_manager()
        mock_handler = AsyncMock()
        mgr._handler_map["test_anima"] = mock_handler
        mgr._app_map["test_anima"] = MagicMock()

        result = await mgr.reload()
        assert result["status"] == "disabled"
        assert not mgr.is_connected

    @patch("server.slack_socket._resolve_bot_user_id", new_callable=AsyncMock, return_value="U_BOT")
    @patch("server.slack_socket.AsyncSocketModeHandler")
    @patch("server.slack_socket.AsyncApp")
    @patch("server.slack_socket.SlackSocketModeManager._discover_per_anima_bots")
    @patch("server.slack_socket.SlackSocketModeManager._get_per_anima_credential")
    @patch("server.slack_socket.load_config")
    async def test_reload_adds_new_handlers(
        self, mock_config, mock_cred, mock_discover, mock_app_cls, mock_handler_cls, mock_resolve,
    ):
        slack_cfg = MagicMock(enabled=True, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )
        mock_discover.return_value = ["sakura", "sumire"]
        mock_cred.return_value = "fake_token"
        mock_app_cls.return_value = MagicMock()
        mock_handler_cls.return_value = AsyncMock()

        mgr = self._make_manager()
        result = await mgr.reload()

        assert result["status"] == "ok"
        assert sorted(result["added"]) == ["sakura", "sumire"]
        assert result["removed"] == []
        assert result["active_handlers"] == 2

    @patch("server.slack_socket.load_config")
    async def test_reload_removes_deleted_handlers(self, mock_config):
        slack_cfg = MagicMock(enabled=True, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )

        mgr = self._make_manager()
        mock_handler = AsyncMock()
        mgr._handler_map["old_anima"] = mock_handler
        mgr._app_map["old_anima"] = MagicMock()
        mgr._bot_user_ids["old_anima"] = "U_OLD"

        with patch.object(type(mgr), "_discover_per_anima_bots", return_value=[]):
            result = await mgr.reload()

        assert result["status"] == "ok"
        assert result["removed"] == ["old_anima"]
        assert result["added"] == []
        mock_handler.close_async.assert_awaited_once()

    @patch("server.slack_socket._resolve_bot_user_id", new_callable=AsyncMock, return_value="U_BOT")
    @patch("server.slack_socket.AsyncSocketModeHandler")
    @patch("server.slack_socket.AsyncApp")
    @patch("server.slack_socket.load_config")
    async def test_reload_diff_add_and_remove(
        self, mock_config, mock_app_cls, mock_handler_cls, mock_resolve,
    ):
        slack_cfg = MagicMock(enabled=True, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )
        mock_app_cls.return_value = MagicMock()
        mock_handler_cls.return_value = AsyncMock()

        mgr = self._make_manager()
        old_handler = AsyncMock()
        mgr._handler_map["old_anima"] = old_handler
        mgr._app_map["old_anima"] = MagicMock()
        mgr._bot_user_ids["old_anima"] = "U_OLD"

        with patch.object(
            type(mgr), "_discover_per_anima_bots", return_value=["new_anima"],
        ), patch.object(
            type(mgr), "_get_per_anima_credential", return_value="fake_token",
        ):
            result = await mgr.reload()

        assert result["added"] == ["new_anima"]
        assert result["removed"] == ["old_anima"]
        assert "new_anima" in mgr._handler_map
        assert "old_anima" not in mgr._handler_map

    @patch("server.slack_socket.load_config")
    async def test_reload_keeps_shared_handler(self, mock_config):
        slack_cfg = MagicMock(enabled=True, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )

        mgr = self._make_manager()
        shared_handler = AsyncMock()
        mgr._handler_map["__shared__"] = shared_handler
        mgr._app_map["__shared__"] = MagicMock()

        with patch.object(type(mgr), "_discover_per_anima_bots", return_value=[]):
            result = await mgr.reload()

        assert "__shared__" in mgr._handler_map
        shared_handler.close_async.assert_not_awaited()

    @patch("server.slack_socket.load_config")
    async def test_reload_no_changes(self, mock_config):
        slack_cfg = MagicMock(enabled=True, mode="socket")
        mock_config.return_value = MagicMock(
            external_messaging=MagicMock(slack=slack_cfg),
        )

        mgr = self._make_manager()
        mgr._handler_map["sakura"] = AsyncMock()
        mgr._app_map["sakura"] = MagicMock()

        with patch.object(type(mgr), "_discover_per_anima_bots", return_value=["sakura"]):
            result = await mgr.reload()

        assert result["added"] == []
        assert result["removed"] == []
        assert result["active_handlers"] == 1


class TestAddPerAnimaHandler:
    """Tests for _add_per_anima_handler()."""

    @patch("server.slack_socket.SlackSocketModeManager._get_per_anima_credential")
    async def test_returns_false_when_missing_credentials(self, mock_cred):
        from server.slack_socket import SlackSocketModeManager

        mock_cred.return_value = None
        mgr = SlackSocketModeManager()
        result = await mgr._add_per_anima_handler("test")
        assert result is False
        assert "test" not in mgr._handler_map

    @patch("server.slack_socket._resolve_bot_user_id", new_callable=AsyncMock, return_value="U_BOT")
    @patch("server.slack_socket.AsyncSocketModeHandler")
    @patch("server.slack_socket.AsyncApp")
    @patch("server.slack_socket.SlackSocketModeManager._get_per_anima_credential")
    async def test_returns_true_on_success(self, mock_cred, mock_app_cls, mock_handler_cls, mock_resolve):
        from server.slack_socket import SlackSocketModeManager

        mock_cred.return_value = "fake_token"
        mock_app_cls.return_value = MagicMock()
        mock_handler_cls.return_value = AsyncMock()

        mgr = SlackSocketModeManager()
        result = await mgr._add_per_anima_handler("sakura")
        assert result is True
        assert "sakura" in mgr._handler_map
        assert "sakura" in mgr._app_map
        mock_handler_cls.return_value.connect_async.assert_awaited_once()

    @patch("server.slack_socket._resolve_bot_user_id", new_callable=AsyncMock, side_effect=RuntimeError("fail"))
    @patch("server.slack_socket.AsyncApp")
    @patch("server.slack_socket.SlackSocketModeManager._get_per_anima_credential")
    async def test_cleans_up_on_failure(self, mock_cred, mock_app_cls, mock_resolve):
        from server.slack_socket import SlackSocketModeManager

        mock_cred.return_value = "fake_token"
        mock_app_cls.return_value = MagicMock()

        mgr = SlackSocketModeManager()
        result = await mgr._add_per_anima_handler("sakura")
        assert result is False
        assert "sakura" not in mgr._handler_map
        assert "sakura" not in mgr._app_map


class TestRemovePerAnimaHandler:
    """Tests for _remove_per_anima_handler()."""

    async def test_remove_existing_handler(self):
        from server.slack_socket import SlackSocketModeManager

        mgr = SlackSocketModeManager()
        mock_handler = AsyncMock()
        mgr._handler_map["test"] = mock_handler
        mgr._app_map["test"] = MagicMock()
        mgr._bot_user_ids["test"] = "U_TEST"

        await mgr._remove_per_anima_handler("test")

        assert "test" not in mgr._handler_map
        assert "test" not in mgr._app_map
        assert "test" not in mgr._bot_user_ids
        mock_handler.close_async.assert_awaited_once()

    async def test_remove_nonexistent_handler(self):
        from server.slack_socket import SlackSocketModeManager

        mgr = SlackSocketModeManager()
        await mgr._remove_per_anima_handler("nonexistent")


class TestBackwardCompatibility:
    """Verify _handlers and _apps properties work."""

    def test_handlers_property(self):
        from server.slack_socket import SlackSocketModeManager

        mgr = SlackSocketModeManager()
        h1 = MagicMock()
        h2 = MagicMock()
        mgr._handler_map["a"] = h1
        mgr._handler_map["b"] = h2
        assert len(mgr._handlers) == 2
        assert h1 in mgr._handlers
        assert h2 in mgr._handlers

    def test_apps_property(self):
        from server.slack_socket import SlackSocketModeManager

        mgr = SlackSocketModeManager()
        a1 = MagicMock()
        mgr._app_map["x"] = a1
        assert a1 in mgr._apps
