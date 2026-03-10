#!/usr/bin/env python3
"""Compare SQLite prompt DB with runtime prompts and code defaults.

Database: ~/.animaworks/tool_prompts.sqlite3
Runtime prompts: ~/.animaworks/prompts/
Code defaults: core/tooling/prompt_db.py

Usage: python scripts/compare_prompt_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
from core.tooling.prompt_db import (
    DEFAULT_DESCRIPTIONS,
    DEFAULT_GUIDES,
)


def main() -> None:
    data_dir = Path.home() / ".animaworks"
    db_path = data_dir / "tool_prompts.sqlite3"
    prompts_dir = data_dir / "prompts"

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    report: list[str] = []
    report.append("=" * 70)
    report.append("PROMPT DB COMPARISON REPORT")
    report.append("=" * 70)

    # ── 1. system_sections ─────────────────────────────────────────────
    report.append("\n## 1. system_sections")
    report.append("-" * 50)

    SECTION_KEY_TO_FILE: dict[str, str | None] = {
        "behavior_rules": "behavior_rules.md",
        "environment": "environment.md",
        "messaging_s": "messaging_s.md",
        "messaging": "messaging.md",
        "communication_rules_s": "communication_rules_s.md",
        "communication_rules": "communication_rules.md",
        "a_reflection": "a_reflection.md",
        "hiring_context": "hiring_context.md",
        "emotion_instruction": None,  # built at runtime
    }

    # Get DB sections
    db_sections = {
        row["key"]: row["content"]
        for row in conn.execute(
            "SELECT key, content FROM system_sections"
        ).fetchall()
    }

    # Compare each expected section
    for key, filename in SECTION_KEY_TO_FILE.items():
        db_content = db_sections.get(key)

        if filename is None:
            # emotion_instruction: built at runtime, just check exists and non-empty
            if key not in db_sections:
                report.append(f"  [MISSING_DB] {key}: not in DB")
            elif not (db_content and db_content.strip()):
                report.append(f"  [DIFF] {key}: in DB but empty")
            else:
                report.append(f"  [OK] {key}: exists and non-empty")
            continue

        filepath = prompts_dir / filename
        if not filepath.exists():
            report.append(f"  [MISSING_DB] {key}: runtime file not found: {filepath}")
            continue

        try:
            runtime_content = filepath.read_text(encoding="utf-8").strip()
        except Exception as e:
            report.append(f"  [DIFF] {key}: failed to read {filepath}: {e}")
            continue

        if key not in db_sections:
            report.append(f"  [MISSING_DB] {key}: not in DB (runtime: {filename})")
        elif db_content.strip() != runtime_content:
            report.append(f"  [DIFF] {key}: DB content differs from {filename}")
        else:
            report.append(f"  [OK] {key}")

    # Extra sections in DB not in code
    expected_keys = set(SECTION_KEY_TO_FILE)
    extra_db = set(db_sections) - expected_keys
    if extra_db:
        for k in sorted(extra_db):
            report.append(f"  [EXTRA_DB] {k}: in DB but not in code mapping")

    # ── 2. tool_descriptions ──────────────────────────────────────────
    report.append("\n## 2. tool_descriptions (locale: ja)")
    report.append("-" * 50)

    code_defaults_ja: dict[str, str] = {}
    for name, loc_dict in DEFAULT_DESCRIPTIONS.items():
        val = loc_dict.get("ja") or loc_dict.get("en") or ""
        code_defaults_ja[name] = val

    db_descriptions = {
        row["name"]: row["description"]
        for row in conn.execute(
            "SELECT name, description FROM tool_descriptions"
        ).fetchall()
    }

    for name in sorted(set(code_defaults_ja) | set(db_descriptions)):
        code_val = code_defaults_ja.get(name)
        db_val = db_descriptions.get(name)

        if name not in db_descriptions:
            report.append(f"  [MISSING_DB] {name}: code default not in DB")
        elif name not in code_defaults_ja:
            report.append(f"  [EXTRA_DB] {name}: in DB but not in DEFAULT_DESCRIPTIONS")
        elif (db_val or "").strip() != (code_val or "").strip():
            report.append(f"  [DIFF] {name}: DB differs from code default")
        else:
            report.append(f"  [OK] {name}")

    # ── 3. tool_guides ────────────────────────────────────────────────
    report.append("\n## 3. tool_guides (locale: ja)")
    report.append("-" * 50)

    code_guides_ja: dict[str, str] = {}
    for key, loc_dict in DEFAULT_GUIDES.items():
        val = loc_dict.get("ja") or loc_dict.get("en") or ""
        code_guides_ja[key] = val

    db_guides = {
        row["key"]: row["content"]
        for row in conn.execute(
            "SELECT key, content FROM tool_guides"
        ).fetchall()
    }

    for key in sorted(set(code_guides_ja) | set(db_guides)):
        code_val = code_guides_ja.get(key)
        db_val = db_guides.get(key)

        if key not in db_guides:
            report.append(f"  [MISSING_DB] {key}: code default not in DB")
        elif key not in code_guides_ja:
            report.append(f"  [EXTRA_DB] {key}: in DB but not in DEFAULT_GUIDES")
        elif (db_val or "").strip() != (code_val or "").strip():
            report.append(f"  [DIFF] {key}: DB differs from code default")
        else:
            report.append(f"  [OK] {key}")

    conn.close()

    # Print report
    for line in report:
        print(line)

    # Summary
    ok_count = sum(1 for l in report if l.strip().startswith("[OK]"))
    diff_count = sum(1 for l in report if l.strip().startswith("[DIFF]"))
    missing_count = sum(1 for l in report if "[MISSING_DB]" in l)
    extra_count = sum(1 for l in report if "[EXTRA_DB]" in l)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  [OK] matches:        {ok_count}")
    print(f"  [DIFF] differences:  {diff_count}")
    print(f"  [MISSING_DB]:        {missing_count}")
    print(f"  [EXTRA_DB]:          {extra_count}")


if __name__ == "__main__":
    main()
