from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Shared session-chaining helper for inline executors (Mode A / Fallback).

Both ``LiteLLMExecutor`` and ``AnthropicFallbackExecutor`` monitor context
usage mid-conversation and save short-term memory when the configured
threshold is crossed.  The next incoming message picks up the saved state
via ``inject_shortterm`` — no in-flight chaining is performed, so the Anima
does not produce an unnatural "session handoff" message mid-conversation.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory.shortterm import StreamCheckpoint

from core.i18n import t
from core.memory import MemoryManager
from core.memory.shortterm import SessionState, ShortTermMemory
from core.paths import load_prompt
from core.prompt.builder import BuildResult
from core.prompt.context import ContextTracker
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.execution.session")


# ── Public helper ─────────────────────────────────────────


async def handle_session_chaining(
    tracker: ContextTracker,
    shortterm: ShortTermMemory | None,
    memory: MemoryManager,
    current_text: str,
    system_prompt_builder: Callable[[], BuildResult | str],
    max_chains: int,
    chain_count: int,
    *,
    session_id: str = "",
    trigger: str = "",
    original_prompt: str = "",
    accumulated_response: str = "",
    turn_count: int = 0,
    tool_uses: list[dict] | None = None,
) -> tuple[str | None, int]:
    """Handle context-threshold session chaining for inline executors.

    When the context tracker indicates the threshold has been crossed and
    chaining is still allowed, this function:

    1. Saves the current session state to short-term memory.
    2. Resets the tracker for a fresh session.
    3. Builds a new system prompt with the short-term memory injected.
    4. Clears the short-term memory file (state is now in the prompt).

    Args:
        tracker: Context usage tracker (must already reflect the latest
            API response).
        shortterm: Short-term memory handle.  If ``None``, chaining is
            skipped.
        memory: ``MemoryManager`` for rebuilding the system prompt.
        current_text: The text produced so far in the current iteration
            (used for logging / accumulated_response).
        system_prompt_builder: Zero-arg callable that returns the base
            system prompt (before short-term injection).  Typically a
            partial of ``build_system_prompt(memory, ...)``.
        max_chains: Maximum number of allowed chain restarts.
        chain_count: How many chains have occurred so far.
        session_id: Identifier for the session origin (e.g.
            ``"litellm-a2"`` or ``"anthropic-fallback"``).
        trigger: Trigger label stored in the ``SessionState``.
        original_prompt: The original user prompt (stored in state).
        accumulated_response: All response text accumulated before this
            call (the ``current_text`` is appended automatically).
        turn_count: Number of LLM turns executed so far.
        tool_uses: List of tool-use dicts (``name``, ``input``,
            ``result``) extracted from the conversation messages.

    Returns:
        A 2-tuple ``(new_system_prompt, new_chain_count)``:
        - ``new_system_prompt`` is always ``None`` — chaining is deferred to
          the next incoming message so the Anima does not produce an
          unnatural "session handoff" message mid-response.
        - ``new_chain_count`` is the (unchanged) chain counter.
    """
    if shortterm is None:
        return None, chain_count

    if not tracker.threshold_exceeded:
        return None, chain_count

    if chain_count >= max_chains:
        return None, chain_count

    logger.info(
        "Session context at %.1f%% — saving shortterm, will resume on next message",
        tracker.usage_ratio * 100,
    )

    # Combine accumulated text with the latest response fragment
    full_accumulated = accumulated_response
    if current_text:
        full_accumulated = f"{accumulated_response}\n{current_text}" if accumulated_response else current_text

    shortterm.save(
        SessionState(
            session_id=session_id,
            timestamp=now_iso(),
            trigger=trigger,
            original_prompt=original_prompt,
            accumulated_response=full_accumulated,
            tool_uses=tool_uses or [],
            context_usage_ratio=tracker.usage_ratio,
            turn_count=turn_count,
        )
    )

    # Do NOT chain here. The shortterm file is now ready and will be
    # injected into the system prompt when the next message arrives
    # (_agent_cycle.py: inject_shortterm called if shortterm.has_pending()).
    return None, chain_count


def build_continuation_prompt() -> str:
    """Load the session continuation prompt template.

    Convenience wrapper so callers need not import ``core.paths`` directly.
    """
    return load_prompt("session_continuation")


def build_stream_retry_prompt(checkpoint: StreamCheckpoint) -> str:
    """Build a continuation prompt from a stream checkpoint.

    Summarises what was completed before the disconnect and instructs the
    LLM to continue from where it left off.

    Args:
        checkpoint: The checkpoint recorded during the interrupted stream.

    Returns:
        A prompt string for the retry session.
    """

    completed_lines: list[str] = []
    for i, tool in enumerate(checkpoint.completed_tools, 1):
        name = tool.get("tool_name", "unknown")
        summary = tool.get("summary", "")
        completed_lines.append(f"{i}. ✅ {name}: {summary}")

    completed_section = "\n".join(completed_lines) if completed_lines else t("session.completed_none")

    # Truncate accumulated text to avoid oversized prompt
    acc_text = checkpoint.accumulated_text
    if len(acc_text) > 2000:
        acc_text = t("session.text_truncated") + "\n" + acc_text[-2000:]

    return (
        t("session.continuation_intro") + "\n"
        "\n"
        f"{t('session.original_instruction_header')}\n"
        f"{checkpoint.original_prompt}\n"
        "\n"
        f"{t('session.completed_steps_header')}\n"
        f"{completed_section}\n"
        "\n"
        f"{t('session.output_so_far_header')}\n"
        f"{acc_text}\n"
        "\n"
        f"{t('session.caution_header')}\n"
        f"- {t('session.caution_no_repeat')}\n"
        f"- {t('session.caution_skip_existing')}\n"
        f"- {t('session.caution_continue')}\n"
    )
