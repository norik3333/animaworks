# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""AnimaWorks external tools package."""
from __future__ import annotations
import logging
import sys
from pathlib import Path

logger = logging.getLogger("animaworks.tools")


def discover_core_tools() -> dict[str, str]:
    """Scan core/tools/ for tool modules.

    Returns: Mapping of tool_name → module path (e.g., "core.tools.web_search").
    Skips files starting with _ (private/internal modules).
    """
    tools_dir = Path(__file__).parent
    core: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        core[tool_name] = f"core.tools.{tool_name}"
    return core


# Backward-compatible module-level variable
TOOL_MODULES = discover_core_tools()


def discover_common_tools(data_dir: Path | None = None) -> dict[str, str]:
    """Scan ~/.animaworks/common_tools/ for shared tool modules.

    Returns: Mapping of tool_name → absolute file path.
    """
    if data_dir is None:
        from core.paths import get_data_dir
        data_dir = get_data_dir()
    tools_dir = data_dir / "common_tools"
    if not tools_dir.is_dir():
        return {}
    common: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Common tool '%s' shadows core tool — skipped", tool_name,
            )
            continue
        common[tool_name] = str(f)
    if common:
        logger.info("Discovered common tools: %s", list(common.keys()))
    return common


def discover_personal_tools(person_dir: Path) -> dict[str, str]:
    """Scan ``{person_dir}/tools/`` for personal tool modules.

    Returns:
        Mapping of tool_name → absolute file path.
        Skips files starting with ``_`` (including ``__init__.py``).
    """
    tools_dir = person_dir / "tools"
    if not tools_dir.is_dir():
        return {}
    personal: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Personal tool '%s' shadows core tool — skipped", tool_name,
            )
            continue
        personal[tool_name] = str(f)
    if personal:
        logger.info("Discovered personal tools: %s", list(personal.keys()))
    return personal


def cli_dispatch():
    """Entry point for ``animaworks-tool`` CLI command.

    Supports core tools (from ``TOOL_MODULES``), common tools
    (from ``common_tools/``), and personal tools discovered via
    the ``ANIMAWORKS_PERSON_DIR`` environment variable.
    """
    import os

    # Discover common tools
    common = discover_common_tools()

    # Discover personal tools if person_dir is set
    person_dir_str = os.environ.get("ANIMAWORKS_PERSON_DIR", "")
    personal: dict[str, str] = {}
    if person_dir_str:
        personal = discover_personal_tools(Path(person_dir_str))

    all_tools = set(TOOL_MODULES.keys()) | set(common.keys()) | set(personal.keys())

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        tools = ", ".join(sorted(all_tools))
        print(f"Usage: animaworks-tool <tool_name> [args...]")
        print(f"Available tools: {tools}")
        sys.exit(0 if "--help" in sys.argv else 1)

    tool_name = sys.argv[1]

    # Try core tools first
    if tool_name in TOOL_MODULES:
        import importlib
        mod = importlib.import_module(TOOL_MODULES[tool_name])
        if not hasattr(mod, "cli_main"):
            print(f"Tool '{tool_name}' has no CLI interface")
            sys.exit(1)
        mod.cli_main(sys.argv[2:])
        return

    # Try common or personal tools (loaded from file path)
    file_tool = personal.get(tool_name) or common.get(tool_name)
    if file_tool:
        import importlib.util
        origin = "personal" if tool_name in personal else "common"
        spec = importlib.util.spec_from_file_location(
            f"animaworks_{origin}_tool_{tool_name}", file_tool,
        )
        if spec is None or spec.loader is None:
            print(f"Cannot load {origin} tool: {tool_name}")
            sys.exit(1)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        if not hasattr(mod, "cli_main"):
            print(f"{origin.capitalize()} tool '{tool_name}' has no CLI interface")
            sys.exit(1)
        mod.cli_main(sys.argv[2:])
        return

    print(f"Unknown tool: {tool_name}")
    print(f"Available: {', '.join(sorted(all_tools))}")
    sys.exit(1)