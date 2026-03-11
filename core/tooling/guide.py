from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Dynamic tool guide generation for Mode S (CLI) and Mode A (schema).

.. deprecated::
    External tools are now accessed via ``use_tool`` (Mode B) or
    skill+CLI (Mode A/S).  ``build_tools_guide()`` returns an empty
    string.  ``load_tool_schemas()`` delegates to
    ``schemas.load_all_tool_schemas()``.
"""

import importlib
import logging
import re
from typing import Any

logger = logging.getLogger("animaworks.tool_guide")


# ── Gated action filtering ───────────────────────────────────────


def _get_gated_actions(tool_name: str) -> set[str]:
    """Return action names marked gated: True in the tool's EXECUTION_PROFILE.

    Args:
        tool_name: Tool module name (e.g. ``gmail``, ``image_gen``).

    Returns:
        Set of action/subcommand names that are gated.
    """
    try:
        from core.tools import TOOL_MODULES

        if tool_name not in TOOL_MODULES:
            return set()
        mod = importlib.import_module(TOOL_MODULES[tool_name])
        profile = getattr(mod, "EXECUTION_PROFILE", None)
        if not isinstance(profile, dict):
            return set()
        return {action for action, info in profile.items() if isinstance(info, dict) and info.get("gated") is True}
    except Exception:
        logger.debug("Failed to load EXECUTION_PROFILE for %s", tool_name, exc_info=True)
        return set()


def filter_gated_from_guide(
    guide_text: str,
    tool_name: str,
    permitted: set[str],
) -> str:
    """Remove CLI guide lines for gated actions that are not permitted.

    For each action in the tool's EXECUTION_PROFILE with gated=True,
    if ``{tool_name}_{action}`` is not in permitted, lines containing
    ``animaworks-tool {tool_name} {action}`` are removed.

    Args:
        guide_text: Raw CLI guide text (e.g. from get_cli_guide or skill content).
        tool_name: Tool module name (e.g. ``gmail``, ``image_gen``).
        permitted: Set from :func:`core.tooling.permissions.parse_permitted_tools`.

    Returns:
        Filtered guide text with gated action lines removed when not permitted.
    """
    gated = _get_gated_actions(tool_name)
    if not gated:
        return guide_text

    to_remove: set[str] = set()
    for action in gated:
        action_key = f"{tool_name}_{action}"
        if action_key not in permitted:
            to_remove.add(action)

    if not to_remove:
        return guide_text

    escaped_tool = re.escape(tool_name)
    lines: list[str] = []
    for line in guide_text.splitlines():
        keep = True
        for action in to_remove:
            escaped_action = re.escape(action)
            pattern = rf"animaworks-tool\s+{escaped_tool}\s+{escaped_action}\b"
            if re.search(pattern, line):
                keep = False
                break
        if keep:
            lines.append(line)

    return "\n".join(lines)


# ── Public API ───────────────────────────────────────────────────


def build_tools_guide(
    tool_registry: list[str],
    personal_tools: dict[str, str] | None = None,
) -> str:
    """Build a compact summary table of allowed external tools.

    .. deprecated::
        External tools are now accessed via ``use_tool`` with skill-based
        documentation.  This function returns an empty string.
    """
    return ""


def load_tool_schemas(
    tool_registry: list[str],
    personal_tools: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load structured schemas for Mode A.

    Delegates to ``schemas.load_all_tool_schemas()`` which handles both
    core and personal tool modules with consistent normalisation.
    """
    from core.tooling.schemas import load_all_tool_schemas

    return load_all_tool_schemas(
        tool_registry=tool_registry,
        personal_tools=personal_tools,
    )
