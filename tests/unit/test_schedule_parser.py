"""Unit tests for core.schedule_parser module."""
from __future__ import annotations

import pytest
from apscheduler.triggers.cron import CronTrigger

from core.schedule_parser import (
    parse_heartbeat_config,
    parse_cron_md,
    parse_single_cron_task,
    parse_schedule,
    DAY_MAP,
    NTH_DAY_RANGE,
)


class TestParseHeartbeatConfig:
    """Tests for parse_heartbeat_config()."""

    def test_basic_interval_and_active_hours(self):
        content = """# Heartbeat
## 実行間隔
5分ごと
## 活動時間
8:00 - 23:00（JST）
"""
        interval, start, end = parse_heartbeat_config(content)
        assert interval == 5
        assert start == 8
        assert end == 23

    def test_30min_interval(self):
        content = "30分ごと\n活動時間\n9:00 - 22:00"
        interval, start, end = parse_heartbeat_config(content)
        assert interval == 30
        assert start == 9
        assert end == 22

    def test_defaults_when_no_match(self):
        content = "some random content without patterns"
        interval, start, end = parse_heartbeat_config(content)
        assert interval == 30
        assert start == 9
        assert end == 22

    def test_empty_content(self):
        interval, start, end = parse_heartbeat_config("")
        assert interval == 30
        assert start == 9
        assert end == 22


class TestParseCronMd:
    """Tests for parse_cron_md()."""

    def test_single_llm_task(self):
        content = """## 毎朝の業務計画（毎日 9:00 JST）
type: llm
長期記憶から昨日の進捗を確認し、今日のタスクを計画する。
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].name == "毎朝の業務計画"
        assert tasks[0].schedule == "毎日 9:00 JST"
        assert tasks[0].type == "llm"
        assert "長期記憶" in tasks[0].description

    def test_multiple_tasks(self):
        content = """## Task A（毎日 8:00 JST）
type: llm
Description A

## Task B（毎週金曜 17:00 JST）
type: llm
Description B
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 2
        assert tasks[0].name == "Task A"
        assert tasks[1].name == "Task B"

    def test_command_type(self):
        content = """## Backup（毎日 2:00 JST）
type: command
command: /usr/bin/backup.sh
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].type == "command"
        assert tasks[0].command == "/usr/bin/backup.sh"

    def test_default_type_is_llm(self):
        content = """## Task（毎日 9:00）
Description without type
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].type == "llm"

    def test_empty_content(self):
        tasks = parse_cron_md("")
        assert tasks == []

    def test_tool_type_with_args(self):
        content = """## Slack通知（平日 9:00 JST）
type: command
tool: slack_post
args:
  channel: general
  message: おはようございます
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].tool == "slack_post"
        assert tasks[0].args == {"channel": "general", "message": "おはようございます"}


class TestParseSchedule:
    """Tests for parse_schedule()."""

    def test_daily(self):
        trigger = parse_schedule("毎日 9:00 JST")
        assert trigger is not None
        assert isinstance(trigger, CronTrigger)

    def test_weekday(self):
        trigger = parse_schedule("平日 9:00 JST")
        assert trigger is not None

    def test_weekly(self):
        trigger = parse_schedule("毎週金曜 17:00 JST")
        assert trigger is not None

    def test_biweekly(self):
        trigger = parse_schedule("隔週金曜 17:00 JST")
        assert trigger is not None

    def test_nth_weekday(self):
        trigger = parse_schedule("第2火曜 10:00 JST")
        assert trigger is not None

    def test_monthly_day(self):
        trigger = parse_schedule("毎月1日 9:00 JST")
        assert trigger is not None

    def test_monthly_last_day(self):
        trigger = parse_schedule("毎月最終日 18:00 JST")
        assert trigger is not None

    def test_standard_cron(self):
        trigger = parse_schedule("*/5 * * * *")
        assert trigger is not None

    def test_invalid_returns_none(self):
        trigger = parse_schedule("invalid schedule string")
        assert trigger is None

    def test_empty_returns_none(self):
        trigger = parse_schedule("")
        assert trigger is None


class TestConstants:
    """Tests for module constants."""

    def test_day_map_completeness(self):
        assert len(DAY_MAP) == 7
        assert "月曜" in DAY_MAP
        assert "日曜" in DAY_MAP

    def test_nth_day_range(self):
        assert NTH_DAY_RANGE[1] == "1-7"
        assert NTH_DAY_RANGE[4] == "22-28"
