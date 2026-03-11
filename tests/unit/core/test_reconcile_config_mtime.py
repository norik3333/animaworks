"""Unit tests for ReconcileMixin._check_config_freshness()."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch



class FakeReconcileMixin:
    """Minimal stand-in that inherits _check_config_freshness from the mixin."""

    def __init__(self):
        pass

    # Import the method from the actual mixin
    from core.supervisor._mgr_reconcile import ReconcileMixin
    _check_config_freshness = ReconcileMixin._check_config_freshness


class TestCheckConfigFreshness:
    """Tests for the config mtime detection in the reconciliation loop."""

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_first_call_stores_mtime(self, mock_path, mock_load):
        mock_stat = MagicMock()
        mock_stat.st_mtime = 1000.0
        mock_path.return_value = MagicMock(stat=MagicMock(return_value=mock_stat))

        obj = FakeReconcileMixin()
        obj._check_config_freshness()

        assert obj._last_config_mtime == 1000.0
        mock_load.assert_not_called()

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_no_change_does_not_reload(self, mock_path, mock_load):
        mock_stat = MagicMock()
        mock_stat.st_mtime = 1000.0
        mock_path.return_value = MagicMock(stat=MagicMock(return_value=mock_stat))

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # first call — stores
        obj._check_config_freshness()  # second call — same mtime

        mock_load.assert_not_called()

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_mtime_change_triggers_reload(self, mock_path, mock_load):
        mock_stat = MagicMock()
        mock_stat.st_mtime = 1000.0
        mock_path_obj = MagicMock(stat=MagicMock(return_value=mock_stat))
        mock_path.return_value = mock_path_obj

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # stores mtime=1000

        mock_stat.st_mtime = 2000.0
        obj._check_config_freshness()  # detects change

        mock_load.assert_called_once()
        assert obj._last_config_mtime == 2000.0

    @patch("core.config.models.get_config_path")
    def test_exception_is_silently_caught(self, mock_path):
        mock_path.side_effect = RuntimeError("boom")

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # should not raise

    @patch("core.config.models.load_config")
    @patch("core.config.models.get_config_path")
    def test_multiple_changes_trigger_multiple_reloads(self, mock_path, mock_load):
        mock_stat = MagicMock()
        mock_stat.st_mtime = 100.0
        mock_path.return_value = MagicMock(stat=MagicMock(return_value=mock_stat))

        obj = FakeReconcileMixin()
        obj._check_config_freshness()  # stores 100

        mock_stat.st_mtime = 200.0
        obj._check_config_freshness()  # change 1
        assert mock_load.call_count == 1

        mock_stat.st_mtime = 300.0
        obj._check_config_freshness()  # change 2
        assert mock_load.call_count == 2
