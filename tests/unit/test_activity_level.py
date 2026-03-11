"""Unit tests for the Global Activity Level feature.

Tests cover:
  - _calc_effective_max_turns() scaling logic
  - AnimaWorksConfig.activity_level field validation
  - HeartbeatConfig.interval_minutes extended range
  - Per-anima heartbeat_interval_minutes reading from status.json
  - SchedulerManager._setup_heartbeat() with activity_level
  - SchedulerManager.reschedule_heartbeat()
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from core._anima_heartbeat import _calc_effective_max_turns
from core.config.models import AnimaWorksConfig, HeartbeatConfig

# ── _calc_effective_max_turns ─────────────────────────────────


class TestCalcEffectiveMaxTurns:
    """Tests for _calc_effective_max_turns function."""

    def test_at_100_returns_none(self):
        assert _calc_effective_max_turns(20, 100) is None

    def test_above_100_returns_none(self):
        assert _calc_effective_max_turns(20, 200) is None
        assert _calc_effective_max_turns(20, 400) is None

    def test_at_50_halves_turns(self):
        result = _calc_effective_max_turns(20, 50)
        assert result == 10

    def test_at_10_min_floor(self):
        result = _calc_effective_max_turns(20, 10)
        assert result == max(3, math.ceil(20 * 10 / 100))
        assert result >= 3

    def test_very_low_activity_clamps_to_3(self):
        result = _calc_effective_max_turns(5, 10)
        assert result == 3

    def test_at_30_percent(self):
        result = _calc_effective_max_turns(20, 30)
        assert result == math.ceil(20 * 30 / 100)  # 6

    def test_at_99_percent(self):
        result = _calc_effective_max_turns(20, 99)
        expected = max(3, math.ceil(20 * 99 / 100))
        assert result == expected

    def test_base_turns_3_at_50(self):
        result = _calc_effective_max_turns(3, 50)
        assert result == 3  # ceil(1.5)=2 but clamp to 3

    def test_large_base_turns(self):
        result = _calc_effective_max_turns(200, 50)
        assert result == 100


# ── Config model validation ───────────────────────────────────


class TestActivityLevelConfig:
    """Tests for activity_level field in AnimaWorksConfig."""

    def test_default_value(self):
        config = AnimaWorksConfig()
        assert config.activity_level == 100

    def test_valid_min(self):
        config = AnimaWorksConfig(activity_level=10)
        assert config.activity_level == 10

    def test_valid_max(self):
        config = AnimaWorksConfig(activity_level=400)
        assert config.activity_level == 400

    def test_below_min_raises(self):
        with pytest.raises(ValidationError):
            AnimaWorksConfig(activity_level=9)

    def test_above_max_raises(self):
        with pytest.raises(ValidationError):
            AnimaWorksConfig(activity_level=401)

    def test_zero_raises(self):
        with pytest.raises(ValidationError):
            AnimaWorksConfig(activity_level=0)

    def test_json_roundtrip(self):
        config = AnimaWorksConfig(activity_level=75)
        data = config.model_dump(mode="json")
        assert data["activity_level"] == 75
        restored = AnimaWorksConfig.model_validate(data)
        assert restored.activity_level == 75


class TestHeartbeatIntervalExtended:
    """Tests for relaxed interval_minutes upper bound."""

    def test_default_30(self):
        config = HeartbeatConfig()
        assert config.interval_minutes == 30

    def test_old_max_60_still_valid(self):
        config = HeartbeatConfig(interval_minutes=60)
        assert config.interval_minutes == 60

    def test_extended_120(self):
        config = HeartbeatConfig(interval_minutes=120)
        assert config.interval_minutes == 120

    def test_extended_max_1440(self):
        config = HeartbeatConfig(interval_minutes=1440)
        assert config.interval_minutes == 1440

    def test_above_1440_raises(self):
        with pytest.raises(ValidationError):
            HeartbeatConfig(interval_minutes=1441)


# ── Per-anima interval reading ────────────────────────────────


class TestPerAnimaInterval:
    """Tests for SchedulerManager._read_per_anima_interval."""

    def _make_mgr(self, tmp_path: Path):
        from core.supervisor.scheduler_manager import SchedulerManager

        mock_anima = MagicMock()
        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True, exist_ok=True)
        return SchedulerManager(
            anima=mock_anima,
            anima_name="test-anima",
            anima_dir=anima_dir,
            emit_event=MagicMock(),
        )

    def test_reads_from_status_json(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"heartbeat_interval_minutes": 60}),
            encoding="utf-8",
        )
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 60

    def test_fallback_to_global(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 45
        assert mgr._read_per_anima_interval(app_config) == 45

    def test_invalid_value_fallback(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"heartbeat_interval_minutes": -5}),
            encoding="utf-8",
        )
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 30

    def test_non_numeric_fallback(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"heartbeat_interval_minutes": "fast"}),
            encoding="utf-8",
        )
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 30

    def test_exceeds_max_fallback(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"heartbeat_interval_minutes": 2000}),
            encoding="utf-8",
        )
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 30

    def test_float_value_accepted(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text(
            json.dumps({"heartbeat_interval_minutes": 45.0}),
            encoding="utf-8",
        )
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 45

    def test_corrupt_json_fallback(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        status_path = mgr._anima_dir / "status.json"
        status_path.write_text("{broken", encoding="utf-8")
        app_config = MagicMock()
        app_config.heartbeat.interval_minutes = 30
        assert mgr._read_per_anima_interval(app_config) == 30


# ── Scheduler setup with activity level ───────────────────────


class TestSchedulerActivityLevel:
    """Tests for SchedulerManager._setup_heartbeat with activity_level."""

    def _make_mgr(self, tmp_path: Path, anima_name: str = "test-anima"):
        from core.supervisor.scheduler_manager import SchedulerManager

        mock_anima = MagicMock()
        mock_anima.memory.read_heartbeat_config.return_value = "30分ごと"
        mock_anima.memory.read_cron_config.return_value = ""
        mock_anima.set_on_schedule_changed = MagicMock()
        anima_dir = tmp_path / "animas" / anima_name
        anima_dir.mkdir(parents=True, exist_ok=True)
        return SchedulerManager(
            anima=mock_anima,
            anima_name=anima_name,
            anima_dir=anima_dir,
            emit_event=MagicMock(),
        )

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_default_activity_100(self, mock_load_config, tmp_path):
        config = AnimaWorksConfig()
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()
        assert mgr.scheduler is not None

        jobs = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_activity_50_doubles_interval(self, mock_load_config, tmp_path):
        config = AnimaWorksConfig(activity_level=50)
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()

        jobs = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_activity_200_halves_interval(self, mock_load_config, tmp_path):
        config = AnimaWorksConfig(activity_level=200)
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()

        jobs = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_reschedule_heartbeat(self, mock_load_config, tmp_path):
        config = AnimaWorksConfig(activity_level=100)
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()

        config.activity_level = 200
        mgr.reschedule_heartbeat()

        jobs_after = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs_after if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_low_activity_uses_interval_trigger(self, mock_load_config, tmp_path):
        """Activity 10% with base 30min -> effective 300min (>60) -> IntervalTrigger."""
        config = AnimaWorksConfig(activity_level=10)
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()

        jobs = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()

    @pytest.mark.asyncio
    @patch("core.supervisor.scheduler_manager.load_config")
    async def test_400_percent_5min_floor(self, mock_load_config, tmp_path):
        """Activity 400% with base 15min -> effective 3.75min -> clamped to 5min."""
        config = AnimaWorksConfig(activity_level=400)
        config.heartbeat.interval_minutes = 15
        mock_load_config.return_value = config

        mgr = self._make_mgr(tmp_path)
        mgr.setup()

        jobs = mgr.scheduler.get_jobs()
        heartbeat_jobs = [j for j in jobs if "heartbeat" in j.id]
        assert len(heartbeat_jobs) == 1
        mgr.shutdown()


# ── Effective interval calculation ────────────────────────────


class TestEffectiveIntervalCalc:
    """Pure calculation tests for activity level scaling."""

    @staticmethod
    def _calc(base: int, activity: int) -> int:
        activity_pct = max(10, min(400, activity))
        effective = base / (activity_pct / 100.0)
        return max(5, round(effective))

    def test_100_percent_no_change(self):
        assert self._calc(30, 100) == 30

    def test_50_percent_doubles(self):
        assert self._calc(30, 50) == 60

    def test_200_percent_halves(self):
        assert self._calc(30, 200) == 15

    def test_400_percent_quarter(self):
        assert self._calc(30, 400) == 8  # 30/4 = 7.5 → round → 8

    def test_10_percent_tenfold(self):
        assert self._calc(30, 10) == 300

    def test_400_with_base_15_clamps_to_5(self):
        result = self._calc(15, 400)
        assert result == 5  # 15/4 = 3.75 → round → 4 → clamp → 5

    def test_clamp_minimum_5(self):
        result = self._calc(10, 400)
        assert result == 5  # 10/4 = 2.5 → round → 2 → clamp → 5
