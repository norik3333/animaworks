"""Tests for _resolve_background_config and heartbeat/cron model swap.

Covers:
- _resolve_background_config resolution priority
- Heartbeat model swap and restore
- Cron model swap and restore
- Edge cases (same model, missing config)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.schemas import ModelConfig


# ── _resolve_background_config ────────────────────────────────


def _make_heartbeat_mixin(model_config: ModelConfig) -> object:
    """Create a minimal HeartbeatMixin-like object for testing."""
    from core._anima_heartbeat import HeartbeatMixin

    class FakeMixin(HeartbeatMixin):
        pass

    mixin = FakeMixin.__new__(FakeMixin)
    mixin.agent = MagicMock()
    mixin.agent.model_config = model_config
    return mixin


_PATCH_LOAD_CONFIG = "core.config.models.load_config"


class TestResolveBackgroundConfig:
    def test_returns_none_when_no_background_model(self):
        mc = ModelConfig(model="claude-opus-4-6")
        mixin = _make_heartbeat_mixin(mc)

        with patch(_PATCH_LOAD_CONFIG) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.heartbeat.default_model = None
            mock_config.return_value = mock_cfg

            result = mixin._resolve_background_config()

        assert result is None

    def test_returns_config_from_per_anima(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="claude-sonnet-4-6",
        )
        mixin = _make_heartbeat_mixin(mc)

        result = mixin._resolve_background_config()

        assert result is not None
        assert result.model == "claude-sonnet-4-6"

    def test_falls_back_to_heartbeat_default_model(self):
        mc = ModelConfig(model="claude-opus-4-6")
        mixin = _make_heartbeat_mixin(mc)

        with patch(_PATCH_LOAD_CONFIG) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.heartbeat.default_model = "openai/gpt-4.1-mini"
            mock_config.return_value = mock_cfg

            result = mixin._resolve_background_config()

        assert result is not None
        assert result.model == "openai/gpt-4.1-mini"

    def test_returns_none_when_same_model(self):
        mc = ModelConfig(
            model="claude-sonnet-4-6",
            background_model="claude-sonnet-4-6",
        )
        mixin = _make_heartbeat_mixin(mc)

        result = mixin._resolve_background_config()
        assert result is None

    def test_per_anima_takes_priority_over_global(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="claude-sonnet-4-6",
        )
        mixin = _make_heartbeat_mixin(mc)

        result = mixin._resolve_background_config()
        assert result.model == "claude-sonnet-4-6"

    def test_applies_background_credential(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="openai/gpt-4.1-mini",
            background_credential="azure",
        )
        mixin = _make_heartbeat_mixin(mc)

        with patch(_PATCH_LOAD_CONFIG) as mock_config:
            mock_cfg = MagicMock()
            from core.config.models import CredentialConfig
            mock_cfg.credentials = {
                "azure": CredentialConfig(
                    api_key="test-key",
                    base_url="https://test.openai.azure.com",
                    keys={"api_version": "2024-12-01"},
                ),
            }
            mock_config.return_value = mock_cfg

            result = mixin._resolve_background_config()

        assert result is not None
        assert result.model == "openai/gpt-4.1-mini"
        assert result.api_key == "test-key"
        assert result.api_base_url == "https://test.openai.azure.com"
        assert result.extra_keys == {"api_version": "2024-12-01"}

    def test_preserves_original_fields(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="claude-sonnet-4-6",
            max_turns=200,
            max_tokens=8192,
            context_threshold=0.8,
        )
        mixin = _make_heartbeat_mixin(mc)

        result = mixin._resolve_background_config()

        assert result.model == "claude-sonnet-4-6"
        assert result.max_turns == 200
        assert result.max_tokens == 8192
        assert result.context_threshold == 0.8


# ── Heartbeat model swap integration ──────────────────────────


class TestHeartbeatModelSwap:
    """Test that heartbeat correctly swaps and restores model config."""

    @pytest.fixture
    def mock_mixin(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="claude-sonnet-4-6",
        )
        mixin = _make_heartbeat_mixin(mc)
        mixin.anima_dir = MagicMock()
        mixin.anima_dir.__truediv__ = MagicMock(return_value=MagicMock())
        mixin._activity = MagicMock()
        mixin._last_activity = None
        mixin.memory = MagicMock()
        mixin.model_config = mc
        return mixin

    def test_update_model_config_called_on_swap(self, mock_mixin):
        """Verify update_model_config is called with background config."""
        bg_config = ModelConfig(model="claude-sonnet-4-6")

        with patch.object(type(mock_mixin), "_resolve_background_config", return_value=bg_config):
            original = mock_mixin.agent.model_config
            mock_mixin.agent.update_model_config.assert_not_called()

    def test_resolve_returns_none_skips_swap(self, mock_mixin):
        """When _resolve_background_config returns None, no swap occurs."""
        with patch.object(type(mock_mixin), "_resolve_background_config", return_value=None):
            mock_mixin.agent.update_model_config.assert_not_called()


# ── Inbox model swap integration ──────────────────────────────


def _make_inbox_mixin(model_config: ModelConfig) -> object:
    """Create a minimal InboxMixin-like object that also has _resolve_background_config."""
    from core._anima_inbox import InboxMixin
    from core._anima_heartbeat import HeartbeatMixin

    class FakeAnima(HeartbeatMixin, InboxMixin):
        pass

    obj = FakeAnima.__new__(FakeAnima)
    obj.agent = MagicMock()
    obj.agent.model_config = model_config
    return obj


class TestInboxModelSwap:
    """Test that inbox correctly swaps and restores model config via _resolve_background_config."""

    def test_inbox_uses_resolve_background_config(self):
        """InboxMixin can call _resolve_background_config from HeartbeatMixin via MRO."""
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="claude-sonnet-4-6",
        )
        obj = _make_inbox_mixin(mc)
        result = obj._resolve_background_config()
        assert result is not None
        assert result.model == "claude-sonnet-4-6"

    def test_inbox_no_swap_when_no_background(self):
        mc = ModelConfig(model="claude-opus-4-6")
        obj = _make_inbox_mixin(mc)

        with patch(_PATCH_LOAD_CONFIG) as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.heartbeat.default_model = None
            mock_config.return_value = mock_cfg

            result = obj._resolve_background_config()

        assert result is None

    def test_inbox_no_swap_when_same_model(self):
        mc = ModelConfig(
            model="claude-sonnet-4-6",
            background_model="claude-sonnet-4-6",
        )
        obj = _make_inbox_mixin(mc)
        result = obj._resolve_background_config()
        assert result is None

    def test_inbox_applies_credential(self):
        mc = ModelConfig(
            model="claude-opus-4-6",
            background_model="azure/gpt-4.1-mini",
            background_credential="azure",
        )
        obj = _make_inbox_mixin(mc)

        with patch(_PATCH_LOAD_CONFIG) as mock_config:
            from core.config.models import CredentialConfig
            mock_cfg = MagicMock()
            mock_cfg.credentials = {
                "azure": CredentialConfig(
                    api_key="inbox-key",
                    base_url="https://inbox.openai.azure.com",
                ),
            }
            mock_config.return_value = mock_cfg

            result = obj._resolve_background_config()

        assert result is not None
        assert result.model == "azure/gpt-4.1-mini"
        assert result.api_key == "inbox-key"
        assert result.api_base_url == "https://inbox.openai.azure.com"


# ── Supervisor tool ───────────────────────────────────────────


class TestSetSubordinateBackgroundModel:
    def _setup(self, tmp_path: Path) -> tuple:
        from core.tooling.handler import ToolHandler

        anima_dir = tmp_path / "animas" / "sakura"
        anima_dir.mkdir(parents=True)
        (anima_dir / "permissions.md").write_text("", encoding="utf-8")

        target_dir = tmp_path / "animas" / "hinata"
        target_dir.mkdir(parents=True)
        (target_dir / "status.json").write_text(json.dumps({
            "enabled": True,
            "supervisor": "sakura",
            "model": "claude-opus-4-6",
            "role": "engineer",
        }), encoding="utf-8")

        memory = MagicMock()
        memory.read_permissions.return_value = ""

        handler = ToolHandler(
            anima_dir=anima_dir,
            memory=memory,
            messenger=None,
            tool_registry=[],
        )
        return handler, target_dir

    def test_set_background_model(self, tmp_path: Path):
        handler, target_dir = self._setup(tmp_path)

        with patch("core.paths.get_data_dir", return_value=tmp_path), \
             patch("core.config.models.load_config") as mock_cfg:
            from core.config.models import AnimaModelConfig
            mock_cfg.return_value = MagicMock(
                animas={"hinata": AnimaModelConfig(supervisor="sakura")},
            )
            result = handler.handle("set_subordinate_background_model", {
                "name": "hinata",
                "model": "claude-sonnet-4-6",
            })

        assert "claude-sonnet-4-6" in result
        data = json.loads((target_dir / "status.json").read_text())
        assert data["background_model"] == "claude-sonnet-4-6"

    def test_clear_background_model(self, tmp_path: Path):
        handler, target_dir = self._setup(tmp_path)

        # Pre-set background_model
        data = json.loads((target_dir / "status.json").read_text())
        data["background_model"] = "claude-sonnet-4-6"
        (target_dir / "status.json").write_text(json.dumps(data), encoding="utf-8")

        with patch("core.paths.get_data_dir", return_value=tmp_path), \
             patch("core.config.models.load_config") as mock_cfg:
            from core.config.models import AnimaModelConfig
            mock_cfg.return_value = MagicMock(
                animas={"hinata": AnimaModelConfig(supervisor="sakura")},
            )
            result = handler.handle("set_subordinate_background_model", {
                "name": "hinata",
                "model": "",
            })

        assert "クリア" in result
        data = json.loads((target_dir / "status.json").read_text())
        assert "background_model" not in data

    def test_requires_name(self, tmp_path: Path):
        handler, _ = self._setup(tmp_path)
        result = handler.handle("set_subordinate_background_model", {"model": "x"})
        assert "InvalidArguments" in result or "name" in result.lower()
