"""Unit tests for core.schedule_parser with standard cron expression format."""
from __future__ import annotations

import logging

import pytest

from core.schedule_parser import (
    parse_cron_md,
    parse_schedule,
    parse_heartbeat_config,
)
from core.schemas import CronTask


# ── parse_cron_md tests ───────────────────────────────────


class TestParseCronMd:
    """Tests for the new cron.md format with ``schedule:`` directives."""

    def test_basic_llm_task(self):
        """Basic LLM-type task with schedule directive."""
        content = """\
## Morning Standup
schedule: 0 9 * * *
type: llm
Check yesterday's progress and plan today.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.name == "Morning Standup"
        assert task.schedule == "0 9 * * *"
        assert task.type == "llm"
        assert "progress" in task.description

    def test_command_type_with_bash(self):
        """Command-type task with bash command."""
        content = """\
## DB Backup
schedule: 0 2 * * *
type: command
command: /usr/local/bin/backup.sh
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.name == "DB Backup"
        assert task.schedule == "0 2 * * *"
        assert task.type == "command"
        assert task.command == "/usr/local/bin/backup.sh"

    def test_command_type_with_tool_and_args(self):
        """Command-type task with tool and YAML args."""
        content = """\
## Deploy
schedule: 0 2 * * 1-5
type: command
tool: run_deploy
args:
  env: staging
  dry_run: true
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        task = tasks[0]
        assert task.name == "Deploy"
        assert task.schedule == "0 2 * * 1-5"
        assert task.type == "command"
        assert task.tool == "run_deploy"
        assert task.args == {"env": "staging", "dry_run": True}

    def test_multiple_tasks(self):
        """Multiple tasks in one cron.md."""
        content = """\
## Morning Report
schedule: 0 9 * * *
type: llm
Summarize overnight events.

## Evening Cleanup
schedule: 30 17 * * 1-5
type: command
command: /opt/cleanup.sh
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 2
        assert tasks[0].name == "Morning Report"
        assert tasks[0].schedule == "0 9 * * *"
        assert tasks[1].name == "Evening Cleanup"
        assert tasks[1].schedule == "30 17 * * 1-5"

    def test_every_5_minutes(self):
        """Task running every 5 minutes."""
        content = """\
## Health Check
schedule: */5 * * * *
type: command
tool: health_check
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].schedule == "*/5 * * * *"

    def test_no_schedule_line(self):
        """Task without schedule: line gets empty schedule."""
        content = """\
## Orphan Task
type: llm
Do something without a schedule.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].schedule == ""
        assert tasks[0].name == "Orphan Task"

    def test_default_type_is_llm(self):
        """When type: is missing, defaults to llm."""
        content = """\
## Simple Task
schedule: 0 12 * * *
Just do something at noon.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].type == "llm"

    def test_empty_content(self):
        """Empty content returns no tasks."""
        assert parse_cron_md("") == []
        assert parse_cron_md("   \n  \n") == []


# ── HTML comment tests ────────────────────────────────────


class TestHtmlCommentExclusion:
    """Tests for HTML comment stripping before cron.md parsing."""

    def test_html_comment_single_line_excluded(self):
        """A task fully wrapped in a single HTML comment block is excluded."""
        content = """\
<!-- ## Disabled Task
schedule: 0 9 * * *
type: llm
Do something disabled -->
"""
        tasks = parse_cron_md(content)
        assert tasks == []

    def test_html_comment_multiline_excluded(self):
        """Multiple tasks inside one HTML comment block are all excluded."""
        content = """\
<!--
## Task A
schedule: 0 8 * * *
type: llm
Description A

## Task B
schedule: 0 17 * * 5
type: llm
Description B
-->
"""
        tasks = parse_cron_md(content)
        assert tasks == []

    def test_html_comment_partial_exclusion(self):
        """Only commented-out tasks are excluded; tasks outside remain."""
        content = """\
## Active Task
schedule: 0 9 * * *
type: llm
I should be parsed.

<!-- ## Disabled Task
schedule: 0 10 * * *
type: llm
I should NOT be parsed. -->

## Another Active
schedule: 0 8 * * 1-5
type: llm
I should also be parsed.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 2
        assert tasks[0].name == "Active Task"
        assert tasks[1].name == "Another Active"

    def test_no_comments_unchanged(self):
        """Content without HTML comments parses normally (regression)."""
        content = """\
## Daily Report
schedule: 0 18 * * *
type: llm
Summarize the day.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].name == "Daily Report"
        assert tasks[0].schedule == "0 18 * * *"
        assert tasks[0].type == "llm"
        assert "Summarize" in tasks[0].description

    def test_nested_comment_markers(self):
        """Greedy-minimal match: <!-- ... <!-- ... --> stops at first -->."""
        content = """\
<!-- outer <!-- inner --> still visible
## Visible Task
schedule: 0 7 * * *
type: llm
Should be parsed.
"""
        tasks = parse_cron_md(content)
        assert len(tasks) == 1
        assert tasks[0].name == "Visible Task"


# ── parse_schedule tests ──────────────────────────────────


class TestParseSchedule:
    """Tests for parse_schedule with standard cron expressions."""

    def test_daily_at_nine(self):
        """Standard daily 9am cron expression."""
        trigger = parse_schedule("0 9 * * *")
        assert trigger is not None

    def test_every_5_minutes(self):
        """Every 5 minutes cron expression."""
        trigger = parse_schedule("*/5 * * * *")
        assert trigger is not None

    def test_weekday_at_two_am(self):
        """Weekdays at 2am."""
        trigger = parse_schedule("0 2 * * 1-5")
        assert trigger is not None

    def test_friday_at_five_thirty(self):
        """Fridays at 5:30pm."""
        trigger = parse_schedule("30 17 * * 5")
        assert trigger is not None

    def test_first_of_month(self):
        """First of every month at midnight."""
        trigger = parse_schedule("0 0 1 * *")
        assert trigger is not None

    def test_complex_expression(self):
        """Complex cron with ranges and lists."""
        trigger = parse_schedule("0,30 9-17 * * 1-5")
        assert trigger is not None

    def test_every_hour(self):
        """Every hour at minute 0."""
        trigger = parse_schedule("0 * * * *")
        assert trigger is not None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert parse_schedule("") is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string returns None."""
        assert parse_schedule("   ") is None

    def test_invalid_expression_returns_none(self, caplog):
        """Invalid expression returns None with warning."""
        with caplog.at_level(logging.WARNING):
            result = parse_schedule("not a cron expression")
        assert result is None
        assert "Invalid cron expression" in caplog.text

    def test_japanese_schedule_returns_none(self, caplog):
        """Old Japanese format is no longer supported."""
        with caplog.at_level(logging.WARNING):
            result = parse_schedule("毎日 9:00 JST")
        assert result is None
        assert "Invalid cron expression" in caplog.text

    def test_too_few_fields_returns_none(self, caplog):
        """Fewer than 5 fields returns None."""
        with caplog.at_level(logging.WARNING):
            result = parse_schedule("0 9 *")
        assert result is None

    def test_too_many_fields_returns_none(self, caplog):
        """More than 5 fields returns None."""
        with caplog.at_level(logging.WARNING):
            result = parse_schedule("0 9 * * * *")
        assert result is None

    def test_leading_trailing_whitespace_handled(self):
        """Leading/trailing whitespace is stripped."""
        trigger = parse_schedule("  0 9 * * *  ")
        assert trigger is not None


# ── parse_heartbeat_config tests ──────────────────────────


class TestParseHeartbeatConfig:
    """Tests for heartbeat.md parsing (unchanged from previous format)."""

    def test_basic_interval(self):
        """Parse interval from heartbeat content."""
        interval, start, end = parse_heartbeat_config("30分ごとにチェック\n9:00-22:00")
        assert interval == 30
        assert start == 9
        assert end == 22

    def test_custom_interval(self):
        """Parse custom interval."""
        interval, _, _ = parse_heartbeat_config("15分間隔")
        assert interval == 15
