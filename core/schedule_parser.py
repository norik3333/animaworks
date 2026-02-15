from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Schedule-parsing helpers extracted from lifecycle.py.

Provides pure-function parsers for cron.md and heartbeat.md with no
dependency on LifecycleManager or APScheduler internals.
"""

import logging
import re
from typing import Any

import yaml
from apscheduler.triggers.cron import CronTrigger

from core.schemas import CronTask

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────

DAY_MAP = {
    "月曜": "mon",
    "火曜": "tue",
    "水曜": "wed",
    "木曜": "thu",
    "金曜": "fri",
    "土曜": "sat",
    "日曜": "sun",
}

NTH_DAY_RANGE = {
    1: "1-7",
    2: "8-14",
    3: "15-21",
    4: "22-28",
}


# ── Heartbeat parsing ────────────────────────────────────


def parse_heartbeat_config(content: str) -> tuple[int, int, int]:
    """Parse heartbeat.md content to extract scheduling parameters.

    Returns:
        Tuple of (interval_minutes, active_start_hour, active_end_hour)
    """
    interval = 30
    m = re.search(r"(\d+)\s*分", content)
    if m:
        interval = int(m.group(1))

    active_start, active_end = 9, 22
    m = re.search(r"(\d{1,2}):\d{0,2}\s*-\s*(\d{1,2})", content)
    if m:
        active_start, active_end = int(m.group(1)), int(m.group(2))

    return interval, active_start, active_end


# ── Cron parsing ─────────────────────────────────────────


def parse_cron_md(content: str) -> list[CronTask]:
    """Parse cron.md to extract CronTask definitions.

    Supports both LLM-type and command-type tasks:

    LLM-type:
        ## Task Name (schedule)
        type: llm
        Description text...

    Command-type (bash):
        ## Task Name (schedule)
        type: command
        command: /path/to/script.sh

    Command-type (tool):
        ## Task Name (schedule)
        type: command
        tool: tool_name
        args:
          key: value
    """
    tasks: list[CronTask] = []
    cur_name = ""
    cur_sched = ""
    cur_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if cur_name:
                tasks.append(parse_single_cron_task(cur_name, cur_sched, cur_lines))
            header = line[3:].strip()
            sm = re.search(r"[（(](.+?)[）)]", header)
            if sm:
                cur_sched = sm.group(1)
                cur_name = header[: header.find("（" if "（" in header else "(")].strip()
            else:
                cur_name = header
                cur_sched = ""
            cur_lines = []
        elif cur_name:
            cur_lines.append(line)

    if cur_name:
        tasks.append(parse_single_cron_task(cur_name, cur_sched, cur_lines))
    return tasks


def parse_single_cron_task(name: str, schedule: str, lines: list[str]) -> CronTask:
    """Parse a single cron task definition from body lines."""
    task_type = "llm"
    command = None
    tool = None
    args = None
    description_lines: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("type:"):
            task_type = stripped[5:].strip()
        elif stripped.startswith("command:"):
            command = stripped[8:].strip()
        elif stripped.startswith("tool:"):
            tool = stripped[5:].strip()
        elif stripped.startswith("args:"):
            # Parse YAML args block (indented lines following "args:")
            yaml_lines = [line]
            i += 1
            while i < len(lines):
                next_line = lines[i]
                # Continue if line is indented or empty
                if next_line.startswith("  ") or not next_line.strip():
                    yaml_lines.append(next_line)
                    i += 1
                else:
                    break
            i -= 1  # Back one line for outer loop increment

            # Parse YAML
            try:
                parsed = yaml.safe_load("\n".join(yaml_lines))
                if parsed and "args" in parsed:
                    args = parsed["args"]
            except yaml.YAMLError as e:
                logger.warning("Failed to parse args YAML for task %s: %s", name, e)
        else:
            # Regular description line
            description_lines.append(line)

        i += 1

    return CronTask(
        name=name,
        schedule=schedule,
        type=task_type,
        description="\n".join(description_lines).strip(),
        command=command,
        tool=tool,
        args=args,
    )


def parse_schedule(schedule: str) -> CronTrigger | None:
    """Parse a Japanese or standard cron schedule string into a CronTrigger."""
    s = schedule.strip()
    # Remove trailing timezone markers (JST, UTC, etc.)
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)

    # 毎日 9:00
    m = re.match(r"毎日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return CronTrigger(hour=int(m.group(1)), minute=int(m.group(2)))

    # 平日 9:00
    m = re.match(r"平日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return CronTrigger(
            day_of_week="mon-fri", hour=int(m.group(1)), minute=int(m.group(2))
        )

    # 毎週金曜 17:00
    m = re.match(r"毎週(.+?)\s+(\d{1,2}):(\d{2})", s)
    if m:
        day = DAY_MAP.get(m.group(1), "fri")
        return CronTrigger(
            day_of_week=day, hour=int(m.group(2)), minute=int(m.group(3))
        )

    # 隔週金曜 17:00
    m = re.match(r"隔週(.+?)\s+(\d{1,2}):(\d{2})", s)
    if m:
        day = DAY_MAP.get(m.group(1), "fri")
        return CronTrigger(
            day_of_week=day, week="*/2", hour=int(m.group(2)), minute=int(m.group(3))
        )

    # 第2火曜 10:00 (Nth weekday of month)
    m = re.match(r"第(\d)(.+?)\s+(\d{1,2}):(\d{2})", s)
    if m:
        nth = int(m.group(1))
        day = DAY_MAP.get(m.group(2), "mon")
        day_range = NTH_DAY_RANGE.get(nth)
        if day_range:
            return CronTrigger(
                day=day_range,
                day_of_week=day,
                hour=int(m.group(3)),
                minute=int(m.group(4)),
            )

    # 毎月1日 9:00
    m = re.match(r"毎月(\d{1,2})日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return CronTrigger(
            day=int(m.group(1)), hour=int(m.group(2)), minute=int(m.group(3))
        )

    # 毎月最終日 18:00
    m = re.match(r"毎月最終日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return CronTrigger(
            day="last", hour=int(m.group(1)), minute=int(m.group(2))
        )

    # Standard cron: */5 * * * *
    if re.match(r"^[\d\*\/\-\,]+(\s+[\d\*\/\-\,]+){4}$", s):
        parts = s.split()
        return CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
        )

    logger.warning("Could not parse schedule: '%s'", s)
    return None
