from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Monkey-patch for claude-agent-sdk SubprocessCLITransport.close().

Upstream bug: The SDK sends SIGTERM immediately after closing stdin,
killing the Claude Code CLI before it can flush the session JSONL file.
This causes the final assistant text response to be lost from the session,
breaking session resume (the model cannot see its own previous response).

Upstream references:
  - https://github.com/anthropics/claude-agent-sdk-python/pull/614
  - https://github.com/anthropics/claude-code/issues/21971

This patch waits for the CLI subprocess to exit gracefully after stdin EOF
(with a timeout) before sending SIGTERM.  Remove once the SDK ships a fix.
"""

import logging
from contextlib import suppress

logger = logging.getLogger("animaworks.execution.agent_sdk")

_GRACEFUL_EXIT_TIMEOUT_SEC = 5

_patched = False


def apply_sdk_transport_patch() -> None:
    """Patch SubprocessCLITransport.close() to allow graceful CLI shutdown."""
    global _patched  # noqa: PLW0603
    if _patched:
        return

    try:
        import anyio
        from claude_agent_sdk._internal.transport.subprocess_cli import (
            SubprocessCLITransport,
        )
    except ImportError:
        logger.debug("claude_agent_sdk not installed; skipping transport patch")
        return

    _original_close = SubprocessCLITransport.close

    async def _patched_close(self: SubprocessCLITransport) -> None:  # type: ignore[override]
        if not self._process:
            self._ready = False
            return

        # Close stderr task group if active
        if self._stderr_task_group:
            with suppress(Exception):
                self._stderr_task_group.cancel_scope.cancel()
                await self._stderr_task_group.__aexit__(None, None, None)
            self._stderr_task_group = None

        # Close stdin — signals EOF to the CLI subprocess
        async with self._write_lock:
            self._ready = False
            if self._stdin_stream:
                with suppress(Exception):
                    await self._stdin_stream.aclose()
                self._stdin_stream = None

        if self._stderr_stream:
            with suppress(Exception):
                await self._stderr_stream.aclose()
            self._stderr_stream = None

        # --- PATCHED SECTION ---
        # Wait for the CLI to exit gracefully after stdin EOF so it can
        # flush the session JSONL.  Only send SIGTERM on timeout.
        if self._process.returncode is None:
            try:
                with anyio.fail_after(_GRACEFUL_EXIT_TIMEOUT_SEC):
                    await self._process.wait()
            except TimeoutError:
                logger.debug(
                    "CLI did not exit within %ds after stdin EOF; sending SIGTERM",
                    _GRACEFUL_EXIT_TIMEOUT_SEC,
                )
                with suppress(ProcessLookupError):
                    self._process.terminate()
                with suppress(Exception):
                    await self._process.wait()

        self._process = None
        self._stdout_stream = None
        self._stdin_stream = None
        self._stderr_stream = None
        self._exit_error = None

    SubprocessCLITransport.close = _patched_close  # type: ignore[assignment]
    _patched = True
    logger.info(
        "Applied SubprocessCLITransport.close() patch (graceful %ds shutdown before SIGTERM)",
        _GRACEFUL_EXIT_TIMEOUT_SEC,
    )
