# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Migrate legacy config.md files to unified config.json.

Also provides cron.md migration from Japanese text schedules to standard
5-field cron expressions.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("animaworks.config_migrate")

# ── Cron migration constants ─────────────────────────────

# Japanese day-of-week to cron numeric (0=Sun, 1=Mon, ... 6=Sat)
_JP_DAY_TO_CRON: dict[str, str] = {
    "月": "1",
    "火": "2",
    "水": "3",
    "木": "4",
    "金": "5",
    "土": "6",
    "日": "0",
    "月曜": "1",
    "火曜": "2",
    "水曜": "3",
    "木曜": "4",
    "金曜": "5",
    "土曜": "6",
    "日曜": "0",
}


def _parse_config_md(path: Path) -> dict[str, str]:
    """Parse a legacy config.md file and return key-value pairs."""
    raw = path.read_text(encoding="utf-8")
    # Ignore 備考/設定例 sections
    for marker in ("## 備考", "### 設定例"):
        idx = raw.find(marker)
        if idx != -1:
            raw = raw[:idx]

    result = {}
    for m in re.finditer(r"^-\s*(\w+)\s*:\s*(.+)$", raw, re.MULTILINE):
        result[m.group(1).strip()] = m.group(2).strip()
    return result


def _env_name_to_credential_name(env_name: str) -> str:
    """Derive a credential name from an env var name.

    ANTHROPIC_API_KEY -> anthropic
    ANTHROPIC_API_KEY_MYNAME -> anthropic_myname
    OLLAMA_API_KEY -> ollama
    """
    name = env_name.lower()
    # Remove _api_key suffix/infix
    name = re.sub(r"_api_key$", "", name)
    name = re.sub(r"_api_key_", "_", name)
    return name or "default"


def migrate_to_config_json(data_dir: Path) -> None:
    """Build config.json from existing config.md files and environment variables.

    Scans persons_dir for config.md files, parses them, collects credentials,
    and writes a unified config.json.
    """
    from core.config.models import (
        AnimaWorksConfig,
        CredentialConfig,
        PersonModelConfig,
        save_config,
    )

    persons_dir = data_dir / "persons"
    config = AnimaWorksConfig()

    if not persons_dir.exists():
        save_config(config, data_dir / "config.json")
        return

    seen_credentials: dict[str, CredentialConfig] = {}

    for person_dir in sorted(persons_dir.iterdir()):
        if not person_dir.is_dir():
            continue
        config_md = person_dir / "config.md"
        if not config_md.exists():
            continue

        logger.info("Migrating config.md for person: %s", person_dir.name)
        parsed = _parse_config_md(config_md)

        # Determine credential
        api_key_env = parsed.get("api_key_env", "ANTHROPIC_API_KEY")
        base_url = parsed.get("api_base_url", "")
        cred_name = _env_name_to_credential_name(api_key_env)

        if cred_name not in seen_credentials:
            api_key_value = os.environ.get(api_key_env, "")
            seen_credentials[cred_name] = CredentialConfig(
                api_key=api_key_value,
                base_url=base_url or None,
            )

        # Build person config (only override non-default values)
        person_cfg = PersonModelConfig(
            model=parsed.get("model") or None,
            fallback_model=parsed.get("fallback_model") or None,
            max_tokens=int(parsed["max_tokens"]) if "max_tokens" in parsed else None,
            max_turns=int(parsed["max_turns"]) if "max_turns" in parsed else None,
            credential=cred_name,
        )
        config.persons[person_dir.name] = person_cfg

    config.credentials = seen_credentials

    # Ensure at least an "anthropic" credential exists
    if "anthropic" not in config.credentials:
        config.credentials["anthropic"] = CredentialConfig(
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )

    save_config(config, data_dir / "config.json")
    logger.info(
        "Migration complete: %d persons, %d credentials -> %s",
        len(config.persons),
        len(config.credentials),
        data_dir / "config.json",
    )


# ── Cron format migration ────────────────────────────────


def _convert_jp_schedule_to_cron(schedule_text: str) -> str | None:
    """Convert a Japanese schedule string to a 5-field cron expression.

    Args:
        schedule_text: Japanese schedule like ``"毎日 9:00 JST"``

    Returns:
        Cron expression string, or None if the pattern cannot be converted
        automatically (e.g. bi-weekly, nth weekday, last day of month).
    """
    s = schedule_text.strip()
    # Remove trailing timezone markers (JST, UTC, etc.)
    s = re.sub(r"\s+[A-Z]{2,4}$", "", s)

    # X分毎 → */X * * * *
    m = re.match(r"(\d+)分毎", s)
    if m:
        return f"*/{m.group(1)} * * * *"

    # X時間毎 → 0 */X * * *
    m = re.match(r"(\d+)時間毎", s)
    if m:
        return f"0 */{m.group(1)} * * *"

    # 毎日 HH:MM → MM HH * * *
    m = re.match(r"毎日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(2))} {int(m.group(1))} * * *"

    # 平日 HH:MM → MM HH * * 1-5
    m = re.match(r"平日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(2))} {int(m.group(1))} * * 1-5"

    # 毎週X曜 HH:MM → MM HH * * N
    m = re.match(r"毎週(.+?曜?)\s+(\d{1,2}):(\d{2})", s)
    if m:
        day_key = m.group(1)
        day_num = _JP_DAY_TO_CRON.get(day_key)
        if day_num:
            return f"{int(m.group(3))} {int(m.group(2))} * * {day_num}"

    # 毎月DD日 HH:MM → MM HH DD * *
    m = re.match(r"毎月(\d{1,2})日\s+(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(3))} {int(m.group(2))} {int(m.group(1))} * *"

    # Unconvertible patterns: 隔週, 毎月最終日, 第NX曜
    # Return None — caller should handle gracefully
    return None


def _is_already_migrated(content: str) -> bool:
    """Check whether a cron.md file already uses the new ``schedule:`` format.

    Returns True if any ``schedule:`` directive is found in the body
    (not inside an HTML comment).
    """
    stripped = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return bool(re.search(r"^\s*schedule:\s*", stripped, re.MULTILINE))


def migrate_cron_format(person_dir: Path) -> bool:
    """Migrate a person's cron.md from Japanese text schedules to cron expressions.

    Reads the existing cron.md, converts each ``## Title（Schedule）`` section
    to the new format with ``schedule: <cron-expression>``, and writes it back.

    Args:
        person_dir: Path to the person directory containing cron.md.

    Returns:
        True if migration was performed, False if no migration was needed
        (file missing, already migrated, or no convertible schedules).
    """
    cron_md = person_dir / "cron.md"
    if not cron_md.exists():
        return False

    content = cron_md.read_text(encoding="utf-8")
    if not content.strip():
        return False

    # Skip if already migrated
    if _is_already_migrated(content):
        logger.info("cron.md already migrated for %s, skipping", person_dir.name)
        return False

    # Preserve HTML comments by extracting and restoring them
    # We process the raw content line-by-line, handling comment blocks
    output_lines: list[str] = []
    migrated_any = False
    in_comment = False
    section_buffer: list[str] = []
    section_title = ""
    section_schedule = ""

    def _flush_section() -> None:
        """Flush the accumulated section buffer to output_lines."""
        nonlocal migrated_any
        if not section_title:
            output_lines.extend(section_buffer)
            return

        # Try to convert the schedule
        cron_expr = _convert_jp_schedule_to_cron(section_schedule) if section_schedule else None

        if cron_expr:
            # Write new format: ## Title (without schedule in parens)
            output_lines.append(f"## {section_title}")
            output_lines.append(f"schedule: {cron_expr}")
            # Copy body lines (skip empty leading lines)
            for bline in section_buffer:
                output_lines.append(bline)
            migrated_any = True
        elif section_schedule:
            # Unconvertible schedule — keep original title with comment
            output_lines.append(f"## {section_title}")
            output_lines.append(f"<!-- MIGRATION NOTE: could not auto-convert '{section_schedule}' to cron expression -->")
            # Copy body lines as-is
            for bline in section_buffer:
                output_lines.append(bline)
            logger.warning(
                "Could not auto-convert schedule '%s' for task '%s' in %s",
                section_schedule, section_title, person_dir.name,
            )
        else:
            # No schedule at all — keep as-is
            output_lines.append(f"## {section_title}")
            for bline in section_buffer:
                output_lines.append(bline)

    for line in content.splitlines():
        # Track HTML comment state (simple: single-line open/close)
        if "<!--" in line and "-->" not in line:
            in_comment = True
            output_lines.append(line)
            continue
        if in_comment:
            output_lines.append(line)
            if "-->" in line:
                in_comment = False
            continue
        # Single-line comment — pass through
        if "<!--" in line and "-->" in line:
            # Could be a full line comment — check if it's wrapping a section
            # Just pass through
            if not section_title:
                output_lines.append(line)
            else:
                section_buffer.append(line)
            continue

        if line.startswith("## "):
            # Flush previous section
            _flush_section()
            section_buffer = []

            header = line[3:].strip()
            sm = re.search(r"[（(](.+?)[）)]", header)
            if sm:
                section_schedule = sm.group(1)
                section_title = header[: header.find("（" if "（" in header else "(")].strip()
            else:
                section_title = header
                section_schedule = ""
        elif section_title:
            section_buffer.append(line)
        else:
            output_lines.append(line)

    # Flush last section
    _flush_section()

    if not migrated_any:
        return False

    cron_md.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    logger.info("Migrated cron.md for %s", person_dir.name)
    return True


def migrate_all_cron(persons_dir: Path) -> int:
    """Migrate cron.md for all persons in the given directory.

    Args:
        persons_dir: Path to the ``persons/`` directory containing
            per-person subdirectories.

    Returns:
        Number of persons whose cron.md was successfully migrated.
    """
    if not persons_dir.exists():
        logger.info("Persons directory does not exist: %s", persons_dir)
        return 0

    count = 0
    for person_dir in sorted(persons_dir.iterdir()):
        if not person_dir.is_dir():
            continue
        try:
            if migrate_cron_format(person_dir):
                count += 1
        except Exception:
            logger.exception("Failed to migrate cron.md for %s", person_dir.name)

    logger.info("Cron migration complete: %d persons migrated", count)
    return count