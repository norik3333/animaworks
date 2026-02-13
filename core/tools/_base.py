# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Base infrastructure for AnimaWorks tools."""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("animaworks.tools")


class ToolConfigError(Exception):
    """Raised when a tool's configuration is incomplete."""
    pass


@dataclass
class ToolResult:
    """Standardized return value from tool execution."""
    success: bool
    data: Any = None
    text: str = ""
    error: str | None = None


def get_env_or_fail(key: str, tool_name: str) -> str:
    """Get an environment variable, raising a clear error if missing."""
    val = os.environ.get(key)
    if not val:
        raise ToolConfigError(
            f"Tool '{tool_name}' requires environment variable {key}. "
            f"Set it in .env or the shell environment."
        )
    return val