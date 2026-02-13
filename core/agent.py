from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import re
import shlex
import subprocess
import time
from collections.abc import AsyncGenerator, Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

from core.context_tracker import ContextTracker
from core.memory import MemoryManager
from core.messenger import Messenger
from core.paths import load_prompt
from core.prompt_builder import build_system_prompt, inject_shortterm
from core.schemas import CycleResult, ModelConfig
from core.shortterm_memory import SessionState, ShortTermMemory

logger = logging.getLogger("animaworks.agent")

# Type alias for the delegate callback injected by server/app.py.
DelegateFn = Callable[[str, str, str | None], Coroutine[Any, Any, str]]


class AgentCore:
    """Wraps Claude Agent SDK / LiteLLM to provide thinking/acting for a Digital Person.

    Execution modes:
      - A1 (autonomous, Claude):   Claude Agent SDK (claude-agent-sdk)
      - A2 (autonomous, non-Claude): LiteLLM + tool_use loop
      - B  (assisted):              LiteLLM 1-shot, framework handles memory I/O
    """

    def __init__(
        self,
        person_dir: Path,
        memory: MemoryManager,
        model_config: ModelConfig | None = None,
        messenger: Messenger | None = None,
    ) -> None:
        self.person_dir = person_dir
        self.memory = memory
        self.model_config = model_config or ModelConfig()
        self.messenger = messenger
        self._tool_registry = self._init_tool_registry()
        self._sdk_available = self._check_sdk()
        self._delegate_fn: DelegateFn | None = None
        self._agent_lock = asyncio.Lock()

        mode = self._resolve_execution_mode()
        logger.info(
            "AgentCore: model=%s, mode=%s, role=%s, api_key=%s, base_url=%s",
            self.model_config.model,
            mode,
            self.model_config.role or "(none)",
            "direct" if self.model_config.api_key else f"env:{self.model_config.api_key_env}",
            self.model_config.api_base_url or "(default)",
        )

    # ── Delegate callback ──────────────────────────────────

    def set_delegate_fn(self, fn: DelegateFn) -> None:
        """Inject the delegate callback (called from server/app.py)."""
        self._delegate_fn = fn

    # ── Model / mode helpers ───────────────────────────────

    def _is_claude_model(self) -> bool:
        """True if the configured model is a Claude model usable with Agent SDK."""
        m = self.model_config.model
        return m.startswith("claude-") or m.startswith("anthropic/")

    def _resolve_agent_sdk_model(self) -> str:
        """Return the model name suitable for Claude Agent SDK (strip provider prefix)."""
        m = self.model_config.model
        if m.startswith("anthropic/"):
            return m[len("anthropic/"):]
        return m

    def _resolve_execution_mode(self) -> str:
        """Determine the effective execution mode: ``a1``, ``a2``, or ``b``.

        Auto-detection logic (when ``execution_mode`` is None):
          - Claude model + Agent SDK available → a1
          - Non-Claude model → a2
        """
        explicit = self.model_config.execution_mode
        if explicit == "assisted":
            return "b"
        if explicit == "autonomous" or explicit is None:
            if self._is_claude_model() and self._sdk_available:
                return "a1"
            if explicit is None and not self._is_claude_model():
                return "a2"
            # autonomous but non-Claude or SDK unavailable
            return "a2"
        return "a2"

    def _check_sdk(self) -> bool:
        try:
            from claude_agent_sdk import query  # noqa: F401

            return True
        except ImportError:
            logger.warning(
                "claude-agent-sdk not available, falling back to anthropic SDK"
            )
            return False

    def _init_tool_registry(self):
        """Initialize tool registry with tools allowed in permissions.md."""
        try:
            from core.tools import TOOL_MODULES
            # Read permissions to determine allowed tools
            permissions = self.memory.read_permissions() if self.memory else ""
            allowed = []
            if "外部ツール" in permissions:
                for tool_name in TOOL_MODULES:
                    # Check if tool is marked as OK in permissions
                    if f"{tool_name}: OK" in permissions:
                        allowed.append(tool_name)
            return allowed
        except Exception:
            logger.debug("Tool registry initialization skipped")
            return []

    async def run_cycle(
        self, prompt: str, trigger: str = "manual"
    ) -> CycleResult:
        """Run one agent cycle with autonomous memory search.

        Routing:
          - Mode B  (assisted):  ``_run_assisted()``  — 1-shot, no tools
          - Mode A2 (autonomous): ``_run_with_tool_loop()`` — LiteLLM + tool_use
          - Mode A1 (autonomous): ``_run_with_agent_sdk()`` — Claude Agent SDK

        If the context threshold is crossed (A1 only), the session is
        externalized to short-term memory and automatically continued.
        """
        async with self._agent_lock:
            return await self._run_cycle_inner(prompt, trigger)

    async def _run_cycle_inner(
        self, prompt: str, trigger: str
    ) -> CycleResult:
        start = time.monotonic()
        mode = self._resolve_execution_mode()
        logger.info(
            "run_cycle START trigger=%s prompt_len=%d mode=%s",
            trigger, len(prompt), mode,
        )

        # ── Mode B: assisted (1-shot, no tools) ──────────
        if mode == "b":
            result = await self._run_assisted(prompt)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (assisted) trigger=%s duration_ms=%d",
                trigger, duration_ms,
            )
            return CycleResult(
                trigger=trigger,
                action="responded",
                summary=result,
                duration_ms=duration_ms,
            )

        shortterm = ShortTermMemory(self.person_dir)
        tracker = ContextTracker(
            model=self.model_config.model,
            threshold=self.model_config.context_threshold,
        )

        # Build system prompt; inject short-term memory from prior session
        system_prompt = build_system_prompt(self.memory)
        logger.debug("System prompt assembled, length=%d", len(system_prompt))
        if shortterm.has_pending():
            system_prompt = inject_shortterm(system_prompt, shortterm)
            logger.info("Injected short-term memory into system prompt")

        # ── Mode A2: LiteLLM tool_use loop ────────────────
        if mode == "a2":
            result = await self._run_with_tool_loop(
                system_prompt, prompt, tracker, shortterm
            )
            shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (a2) trigger=%s duration_ms=%d response_len=%d",
                trigger, duration_ms, len(result),
            )
            return CycleResult(
                trigger=trigger,
                action="responded",
                summary=result,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
            )

        # ── Mode A1: Claude Agent SDK ─────────────────────
        result, result_msg = await self._run_with_agent_sdk(
            system_prompt, prompt, tracker
        )

        # Session chaining: if threshold was crossed, continue in a new session
        session_chained = False
        total_turns = result_msg.num_turns if result_msg else 0
        chain_count = 0

        while (
            tracker.threshold_exceeded
            and chain_count < self.model_config.max_chains
        ):
            session_chained = True
            chain_count += 1
            logger.info(
                "Session chain %d/%d: context at %.1f%%",
                chain_count,
                self.model_config.max_chains,
                tracker.usage_ratio * 100,
            )

            shortterm.clear()
            shortterm.save(
                SessionState(
                    session_id=result_msg.session_id if result_msg else "",
                    timestamp=datetime.now().isoformat(),
                    trigger=trigger,
                    original_prompt=prompt,
                    accumulated_response=result,
                    context_usage_ratio=tracker.usage_ratio,
                    turn_count=result_msg.num_turns if result_msg else 0,
                )
            )

            tracker.reset()
            system_prompt_2 = inject_shortterm(
                build_system_prompt(self.memory),
                shortterm,
            )
            continuation_prompt = load_prompt("session_continuation")
            try:
                result_2, result_msg_2 = await self._run_with_agent_sdk(
                    system_prompt_2, continuation_prompt, tracker
                )
            except Exception:
                logger.exception(
                    "Chained session %d failed; preserving short-term memory",
                    chain_count,
                )
                break
            result = result + "\n" + result_2
            result_msg = result_msg_2
            if result_msg_2:
                total_turns += result_msg_2.num_turns

        shortterm.clear()

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle END trigger=%s duration_ms=%d response_len=%d chained=%s",
            trigger, duration_ms, len(result), session_chained,
        )
        return CycleResult(
            trigger=trigger,
            action="responded",
            summary=result,
            duration_ms=duration_ms,
            context_usage_ratio=tracker.usage_ratio,
            session_chained=session_chained,
            total_turns=total_turns,
        )

    def _resolve_api_key(self) -> str | None:
        """Resolve the actual API key (direct value from config.json, then env var)."""
        if self.model_config.api_key:
            return self.model_config.api_key
        return os.environ.get(self.model_config.api_key_env)

    # ── Agent SDK path ──────────────────────────────────────

    async def _run_with_agent_sdk(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
    ) -> tuple[str, Any | None]:
        """Run a session via Claude Agent SDK with context monitoring hook.

        Returns ``(response_text, ResultMessage | None)``.
        The second element is typed as ``Any | None`` to avoid importing
        ``ResultMessage`` at module level.
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            HookMatcher,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
            query,
        )
        from claude_agent_sdk.types import (
            HookContext,
            HookInput,
            PostToolUseHookSpecificOutput,
            SyncHookJSONOutput,
        )

        threshold = self.model_config.context_threshold
        _hook_fired = False

        async def _post_tool_hook(
            input_data: HookInput,
            tool_use_id: str | None,
            context: HookContext,
        ) -> SyncHookJSONOutput:
            nonlocal _hook_fired
            transcript_path = input_data.get("transcript_path", "")
            ratio = tracker.estimate_from_transcript(transcript_path)

            if ratio >= threshold and not _hook_fired:
                _hook_fired = True
                logger.info(
                    "PostToolUse hook: context at %.1f%%, injecting save instruction",
                    ratio * 100,
                )
                return SyncHookJSONOutput(
                    hookSpecificOutput=PostToolUseHookSpecificOutput(
                        hookEventName="PostToolUse",
                        additionalContext=(
                            f"コンテキスト使用率が{ratio:.0%}に達しました。"
                            "shortterm/session_state.md に現在の作業状態を書き出してください。"
                            "内容: 何をしていたか、どこまで進んだか、次に何をすべきか。"
                            "書き出し後、作業を中断してその旨を報告してください。"
                        ),
                    )
                )
            return SyncHookJSONOutput()

        # Build env dict so the child process uses per-person credentials
        env: dict[str, str] = {}
        api_key = self._resolve_api_key()
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if self.model_config.api_base_url:
            env["ANTHROPIC_BASE_URL"] = self.model_config.api_base_url

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            permission_mode="acceptEdits",
            cwd=str(self.person_dir),
            max_turns=self.model_config.max_turns,
            model=self._resolve_agent_sdk_model(),
            env=env,
            hooks={
                "PostToolUse": [HookMatcher(matcher=None, hooks=[_post_tool_hook])],
            },
        )

        response_text: list[str] = []
        result_message: ResultMessage | None = None
        message_count = 0
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result_message = message
                tracker.update_from_result_message(message.usage)
            elif isinstance(message, AssistantMessage):
                message_count += 1
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)

        logger.debug(
            "Agent SDK completed, messages=%d text_blocks=%d",
            message_count, len(response_text),
        )
        return "\n".join(response_text) or "(no response)", result_message

    # ── Agent SDK streaming path ─────────────────────────────

    async def _run_with_agent_sdk_streaming(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
    ) -> AsyncGenerator[dict, None]:
        """Stream events from Claude Agent SDK.

        Yields dicts:
            {"type": "text_delta", "text": "..."}
            {"type": "tool_start", "tool_name": "...", "tool_id": "..."}
            {"type": "tool_end", "tool_id": "...", "tool_name": "..."}
            {"type": "done", "full_text": "...", "result_message": ...}
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            HookMatcher,
            ResultMessage,
            TextBlock,
            ToolUseBlock,
            query,
        )
        from claude_agent_sdk.types import (
            HookContext,
            HookInput,
            PostToolUseHookSpecificOutput,
            StreamEvent,
            SyncHookJSONOutput,
        )

        threshold = self.model_config.context_threshold
        _hook_fired = False

        async def _post_tool_hook(
            input_data: HookInput,
            tool_use_id: str | None,
            context: HookContext,
        ) -> SyncHookJSONOutput:
            nonlocal _hook_fired
            transcript_path = input_data.get("transcript_path", "")
            ratio = tracker.estimate_from_transcript(transcript_path)

            if ratio >= threshold and not _hook_fired:
                _hook_fired = True
                logger.info(
                    "PostToolUse hook (stream): context at %.1f%%",
                    ratio * 100,
                )
                return SyncHookJSONOutput(
                    hookSpecificOutput=PostToolUseHookSpecificOutput(
                        hookEventName="PostToolUse",
                        additionalContext=(
                            f"コンテキスト使用率が{ratio:.0%}に達しました。"
                            "shortterm/session_state.md に現在の作業状態を書き出してください。"
                            "内容: 何をしていたか、どこまで進んだか、次に何をすべきか。"
                            "書き出し後、作業を中断してその旨を報告してください。"
                        ),
                    )
                )
            return SyncHookJSONOutput()

        env: dict[str, str] = {}
        api_key = self._resolve_api_key()
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key
        if self.model_config.api_base_url:
            env["ANTHROPIC_BASE_URL"] = self.model_config.api_base_url

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=["Read", "Write", "Edit", "Bash", "Grep", "Glob"],
            permission_mode="acceptEdits",
            cwd=str(self.person_dir),
            max_turns=self.model_config.max_turns,
            model=self._resolve_agent_sdk_model(),
            env=env,
            include_partial_messages=True,
            hooks={
                "PostToolUse": [HookMatcher(matcher=None, hooks=[_post_tool_hook])],
            },
        )

        response_text: list[str] = []
        result_message: ResultMessage | None = None
        active_tool_ids: set[str] = set()
        message_count = 0

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, StreamEvent):
                event = message.event
                event_type = event.get("type", "")

                if event_type == "content_block_start":
                    block = event.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_id = block.get("id", "")
                        active_tool_ids.add(tool_id)
                        yield {
                            "type": "tool_start",
                            "tool_name": block.get("name", ""),
                            "tool_id": tool_id,
                        }

                elif event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield {"type": "text_delta", "text": text}

            elif isinstance(message, AssistantMessage):
                message_count += 1
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        if block.id in active_tool_ids:
                            active_tool_ids.discard(block.id)
                            yield {
                                "type": "tool_end",
                                "tool_id": block.id,
                                "tool_name": block.name,
                            }

            elif isinstance(message, ResultMessage):
                result_message = message
                tracker.update_from_result_message(message.usage)

        logger.debug(
            "Agent SDK streaming completed, messages=%d text_blocks=%d",
            message_count, len(response_text),
        )
        full_text = "\n".join(response_text) or "(no response)"
        yield {
            "type": "done",
            "full_text": full_text,
            "result_message": result_message,
        }

    async def run_cycle_streaming(
        self, prompt: str, trigger: str = "manual"
    ) -> AsyncGenerator[dict, None]:
        """Streaming version of run_cycle.

        Yields stream chunks. Session chaining is handled seamlessly.
        Final event is ``{"type": "cycle_done", "cycle_result": {...}}``.
        """
        start = time.monotonic()
        mode = self._resolve_execution_mode()
        logger.info(
            "run_cycle_streaming START trigger=%s prompt_len=%d mode=%s",
            trigger, len(prompt), mode,
        )

        # Mode B / A2: no streaming support — yield complete text
        if mode in ("b", "a2"):
            async with self._agent_lock:
                cycle = await self._run_cycle_inner(prompt, trigger)
            yield {"type": "text_delta", "text": cycle.summary}
            yield {
                "type": "cycle_done",
                "cycle_result": cycle.model_dump(),
            }
            return

        shortterm = ShortTermMemory(self.person_dir)
        tracker = ContextTracker(
            model=self.model_config.model,
            threshold=self.model_config.context_threshold,
        )

        system_prompt = build_system_prompt(self.memory)
        if shortterm.has_pending():
            system_prompt = inject_shortterm(system_prompt, shortterm)

        # Primary session (A1)
        full_text_parts: list[str] = []
        result_message: Any = None

        async for chunk in self._run_with_agent_sdk_streaming(
            system_prompt, prompt, tracker
        ):
            if chunk["type"] == "done":
                full_text_parts.append(chunk["full_text"])
                result_message = chunk["result_message"]
            else:
                yield chunk

        # Session chaining
        session_chained = False
        total_turns = result_message.num_turns if result_message else 0
        chain_count = 0

        while (
            tracker.threshold_exceeded
            and chain_count < self.model_config.max_chains
        ):
            session_chained = True
            chain_count += 1
            logger.info(
                "Session chain (stream) %d/%d: context at %.1f%%",
                chain_count,
                self.model_config.max_chains,
                tracker.usage_ratio * 100,
            )

            yield {"type": "chain_start", "chain": chain_count}

            shortterm.clear()
            shortterm.save(
                SessionState(
                    session_id=result_message.session_id if result_message else "",
                    timestamp=datetime.now().isoformat(),
                    trigger=trigger,
                    original_prompt=prompt,
                    accumulated_response="\n".join(full_text_parts),
                    context_usage_ratio=tracker.usage_ratio,
                    turn_count=result_message.num_turns if result_message else 0,
                )
            )

            tracker.reset()
            system_prompt_2 = inject_shortterm(
                build_system_prompt(self.memory),
                shortterm,
            )
            continuation_prompt = load_prompt("session_continuation")

            try:
                async for chunk in self._run_with_agent_sdk_streaming(
                    system_prompt_2, continuation_prompt, tracker
                ):
                    if chunk["type"] == "done":
                        full_text_parts.append(chunk["full_text"])
                        result_message = chunk["result_message"]
                        if result_message:
                            total_turns += result_message.num_turns
                    else:
                        yield chunk
            except Exception:
                logger.exception(
                    "Chained session (stream) %d failed", chain_count,
                )
                yield {"type": "error", "message": f"Session chain {chain_count} failed"}
                break

        shortterm.clear()

        full_text = "\n".join(full_text_parts)
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle_streaming END trigger=%s duration_ms=%d response_len=%d chained=%s",
            trigger, duration_ms, len(full_text), session_chained,
        )

        yield {
            "type": "cycle_done",
            "cycle_result": CycleResult(
                trigger=trigger,
                action="responded",
                summary=full_text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                session_chained=session_chained,
                total_turns=total_turns,
            ).model_dump(),
        }

    # ── Anthropic SDK fallback path ─────────────────────────

    async def _run_with_anthropic_sdk(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        shortterm: ShortTermMemory,
    ) -> str:
        """Fallback: use anthropic SDK with tool_use for memory ops.

        Mid-conversation context monitoring: if the threshold is crossed,
        state is externalized and the conversation is restarted with
        restored short-term memory.
        """
        import anthropic

        api_key = self._resolve_api_key()
        client_kwargs: dict[str, str] = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        if self.model_config.api_base_url:
            client_kwargs["base_url"] = self.model_config.api_base_url
        client = anthropic.AsyncAnthropic(**client_kwargs)

        tools = self._build_anthropic_tools()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        all_response_text: list[str] = []
        chain_count = 0

        for iteration in range(10):
            logger.debug(
                "API call iteration=%d messages_count=%d", iteration, len(messages),
            )
            response = await client.messages.create(
                model=self.model_config.model,
                max_tokens=self.model_config.max_tokens,
                system=system_prompt,
                messages=messages,
                tools=tools,
            )

            # Track context usage from API response
            usage_dict = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }
            threshold_crossed = tracker.update_from_usage(usage_dict)

            if threshold_crossed and chain_count < self.model_config.max_chains:
                chain_count += 1
                logger.info(
                    "Anthropic SDK: context threshold crossed at %.1f%%, "
                    "restarting with short-term memory (chain %d/%d)",
                    tracker.usage_ratio * 100,
                    chain_count,
                    self.model_config.max_chains,
                )
                # Collect text so far
                current_text = "\n".join(
                    b.text for b in response.content if b.type == "text"
                )
                all_response_text.append(current_text)

                # Save state
                shortterm.save(
                    SessionState(
                        session_id="anthropic-fallback",
                        timestamp=datetime.now().isoformat(),
                        trigger="anthropic_sdk",
                        original_prompt=prompt,
                        accumulated_response="\n".join(all_response_text),
                        context_usage_ratio=tracker.usage_ratio,
                        turn_count=iteration,
                    )
                )

                # Restart with fresh context + short-term memory
                tracker.reset()
                system_prompt = inject_shortterm(
                    build_system_prompt(self.memory), shortterm
                )
                messages = [
                    {"role": "user", "content": load_prompt("session_continuation")}
                ]
                shortterm.clear()
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                logger.debug("Final response received at iteration=%d", iteration)
                final_text = "\n".join(
                    b.text for b in response.content if b.type == "text"
                )
                all_response_text.append(final_text)
                return "\n".join(all_response_text)

            logger.info(
                "Tool calls at iteration=%d: %s",
                iteration, ", ".join(tu.name for tu in tool_uses),
            )
            messages.append(
                {"role": "assistant", "content": response.content}
            )
            tool_results = []
            for tu in tool_uses:
                if tu.name == "delegate_task":
                    result = await self._handle_delegate_tool_call(tu.input)
                else:
                    result = self._handle_tool_call(tu.name, tu.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        logger.warning("Max iterations (10) reached, returning fallback response")
        return "\n".join(all_response_text) or "(max iterations reached)"

    # ── LiteLLM wrapper ────────────────────────────────────

    async def _call_llm(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> dict:
        """Call LiteLLM ``acompletion`` and return the raw response dict.

        Handles credential resolution (API key + base_url) automatically.
        """
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model_config.model,
            "messages": messages,
            "max_tokens": self.model_config.max_tokens,
        }

        # System prompt — LiteLLM uses it as a system message
        if system:
            kwargs["messages"] = [{"role": "system", "content": system}] + messages

        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        # Credential resolution
        api_key = self._resolve_api_key()
        if api_key:
            kwargs["api_key"] = api_key
        if self.model_config.api_base_url:
            kwargs["api_base"] = self.model_config.api_base_url

        response = await litellm.acompletion(**kwargs)
        return response

    # ── Mode B: assisted (1-shot, framework handles memory) ──

    async def _run_assisted(self, prompt: str) -> str:
        """Mode B execution: framework reads memory, LLM thinks, framework records.

        Flow:
          1. Pre-call: inject identity + recent episodes + keyword-matched knowledge
          2. LLM 1-shot call (no tools)
          3. Post-call: record episode
          4. Post-call: extract knowledge (additional 1-shot)
        """
        logger.info("_run_assisted START prompt_len=%d", len(prompt))

        # ── 1. Pre-call: gather context ──────────────────
        identity = self.memory.read_identity()
        injection = self.memory.read_injection()
        recent_episodes = self.memory.read_recent_episodes(days=7)

        # Simple keyword extraction for knowledge search
        keywords = set(re.findall(r"[\w]{3,}", prompt))
        knowledge_hits: list[str] = []
        for kw in list(keywords)[:10]:
            for fname, line in self.memory.search_memory_text(kw, scope="knowledge"):
                knowledge_hits.append(f"[{fname}] {line}")
        knowledge_context = "\n".join(dict.fromkeys(knowledge_hits))  # dedupe

        # Build enriched system prompt
        system_parts = [identity, injection]
        if recent_episodes:
            system_parts.append(f"## 直近の行動ログ\n\n{recent_episodes[:4000]}")
        if knowledge_context:
            system_parts.append(f"## 関連知識\n\n{knowledge_context[:4000]}")
        system = "\n\n---\n\n".join(p for p in system_parts if p)

        # ── 2. LLM 1-shot call ───────────────────────────
        messages = [{"role": "user", "content": prompt}]
        response = await self._call_llm(messages, system=system)
        reply = response.choices[0].message.content or ""
        logger.info("_run_assisted LLM replied, len=%d", len(reply))

        # ── 3. Post-call: record episode ─────────────────
        ts = datetime.now().strftime("%H:%M")
        episode = f"- {ts} [assisted] prompt: {prompt[:200]}… → reply: {reply[:200]}…"
        self.memory.append_episode(episode)

        # ── 4. Post-call: knowledge extraction ───────────
        try:
            extract_messages = [
                {
                    "role": "user",
                    "content": (
                        "以下のやりとりから、今後の判断に役立つ教訓や事実があれば"
                        "1〜3行で要約してください。なければ「なし」とだけ答えてください。\n\n"
                        f"質問: {prompt[:1000]}\n\n回答: {reply[:1000]}"
                    ),
                }
            ]
            extract_resp = await self._call_llm(extract_messages)
            extracted = extract_resp.choices[0].message.content or ""
            if extracted.strip() and extracted.strip() != "なし":
                topic = datetime.now().strftime("learned_%Y%m%d_%H%M%S")
                self.memory.write_knowledge(topic, extracted.strip())
                logger.info("Knowledge extracted: %s", extracted[:100])
        except Exception:
            logger.debug("Knowledge extraction failed", exc_info=True)

        return reply

    # ── Mode A2: LiteLLM + tool_use loop ─────────────────

    async def _run_with_tool_loop(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        shortterm: ShortTermMemory,
    ) -> str:
        """Mode A2: LiteLLM with tool_use loop.

        The LLM autonomously calls tools (memory, files, commands, delegate)
        until it produces a final text response or hits the iteration limit.
        """
        import litellm

        tools = self._build_a2_tools()
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        all_response_text: list[str] = []

        # Credential resolution
        llm_kwargs: dict[str, Any] = {
            "model": self.model_config.model,
            "max_tokens": self.model_config.max_tokens,
        }
        api_key = self._resolve_api_key()
        if api_key:
            llm_kwargs["api_key"] = api_key
        if self.model_config.api_base_url:
            llm_kwargs["api_base"] = self.model_config.api_base_url

        max_iterations = self.model_config.max_turns
        chain_count = 0

        for iteration in range(max_iterations):
            logger.debug(
                "A2 tool loop iteration=%d messages=%d", iteration, len(messages),
            )
            response = await litellm.acompletion(
                messages=messages,
                tools=[{"type": "function", "function": t} for t in tools],
                **llm_kwargs,
            )

            choice = response.choices[0]
            message = choice.message

            # Track context usage
            if hasattr(response, "usage") and response.usage:
                usage_dict = {
                    "input_tokens": response.usage.prompt_tokens or 0,
                    "output_tokens": response.usage.completion_tokens or 0,
                }
                threshold_crossed = tracker.update_from_usage(usage_dict)
                if threshold_crossed and chain_count < self.model_config.max_chains:
                    chain_count += 1
                    logger.info(
                        "A2: context threshold crossed at %.1f%%, restarting (chain %d/%d)",
                        tracker.usage_ratio * 100, chain_count, self.model_config.max_chains,
                    )
                    current_text = message.content or ""
                    if current_text:
                        all_response_text.append(current_text)
                    shortterm.save(
                        SessionState(
                            session_id="litellm-a2",
                            timestamp=datetime.now().isoformat(),
                            trigger="a2_tool_loop",
                            original_prompt=prompt,
                            accumulated_response="\n".join(all_response_text),
                            context_usage_ratio=tracker.usage_ratio,
                            turn_count=iteration,
                        )
                    )
                    tracker.reset()
                    system_prompt = inject_shortterm(
                        build_system_prompt(self.memory), shortterm
                    )
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": load_prompt("session_continuation")},
                    ]
                    shortterm.clear()
                    continue

            # Check for tool calls (LiteLLM uses function_call / tool_calls)
            tool_calls = message.tool_calls
            if not tool_calls:
                # Final response — no more tool calls
                final_text = message.content or ""
                all_response_text.append(final_text)
                logger.debug("A2 final response at iteration=%d", iteration)
                return "\n".join(all_response_text)

            # Process tool calls
            logger.info(
                "A2 tool calls at iteration=%d: %s",
                iteration,
                ", ".join(tc.function.name for tc in tool_calls),
            )

            # Append assistant message with tool_calls
            messages.append(message.model_dump())

            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = _json.loads(tc.function.arguments)
                except _json.JSONDecodeError:
                    fn_args = {}

                if fn_name == "delegate_task":
                    result = await self._handle_delegate_tool_call(fn_args)
                else:
                    result = self._handle_tool_call(fn_name, fn_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        logger.warning("A2 max iterations (%d) reached", max_iterations)
        return "\n".join(all_response_text) or "(max iterations reached)"

    # ── A2 tool definitions ──────────────────────────────

    def _build_a2_tools(self) -> list[dict]:
        """Build the tool schema list for Mode A2 (LiteLLM function calling format)."""
        tools: list[dict] = [
            # Memory tools (same as Anthropic SDK fallback, restructured for LiteLLM)
            {
                "name": "search_memory",
                "description": "Search the person's long-term memory (knowledge, episodes, procedures) by keyword.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keyword"},
                        "scope": {
                            "type": "string",
                            "enum": ["knowledge", "episodes", "procedures", "all"],
                            "description": "Memory category to search",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_memory_file",
                "description": "Read a file from the person's memory directory by relative path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path within person dir"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_memory_file",
                "description": "Write or append to a file in the person's memory directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "mode": {"type": "string", "enum": ["overwrite", "append"]},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "send_message",
                "description": "Send a message to another person.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Recipient person name"},
                        "content": {"type": "string", "description": "Message content"},
                        "reply_to": {"type": "string", "description": "Message ID to reply to"},
                        "thread_id": {"type": "string", "description": "Thread ID"},
                    },
                    "required": ["to", "content"],
                },
            },
            # File operations (new for A2)
            {
                "name": "read_file",
                "description": "Read an arbitrary file (subject to permissions).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute file path"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write content to a file (subject to permissions).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute file path"},
                        "content": {"type": "string", "description": "File content"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "edit_file",
                "description": "Replace a specific string in a file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute file path"},
                        "old_string": {"type": "string", "description": "Text to find"},
                        "new_string": {"type": "string", "description": "Replacement text"},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            },
            {
                "name": "execute_command",
                "description": "Execute a shell command (subject to permissions allow-list).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to run"},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default 30)",
                        },
                    },
                    "required": ["command"],
                },
            },
        ]

        # Delegate tool (only for commanders or persons with delegate_fn)
        if self._delegate_fn and self.model_config.role == "commander":
            tools.append({
                "name": "delegate_task",
                "description": "Delegate a task to a subordinate person and wait for the result.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "Subordinate person name"},
                        "task": {"type": "string", "description": "Task instruction"},
                        "context": {"type": "string", "description": "Background context (optional)"},
                    },
                    "required": ["to", "task"],
                },
            })

        # External tools from registry
        if self._tool_registry:
            try:
                import importlib
                from core.tools import TOOL_MODULES
                for tool_name in self._tool_registry:
                    if tool_name in TOOL_MODULES:
                        mod = importlib.import_module(TOOL_MODULES[tool_name])
                        if hasattr(mod, "get_tool_schemas"):
                            for schema in mod.get_tool_schemas():
                                # Convert from Anthropic format to LiteLLM function format
                                tools.append({
                                    "name": schema["name"],
                                    "description": schema.get("description", ""),
                                    "parameters": schema.get("input_schema", {}),
                                })
            except Exception:
                logger.debug("Failed to load external tool schemas for A2", exc_info=True)

        return tools

    # ── Tool definitions (Anthropic SDK fallback) ───────────

    def _build_anthropic_tools(self) -> list[dict]:
        tools = [
            {
                "name": "search_memory",
                "description": "Search the person's long-term memory by keyword.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search keyword",
                        },
                        "scope": {
                            "type": "string",
                            "enum": [
                                "knowledge",
                                "episodes",
                                "procedures",
                                "all",
                            ],
                            "description": "Memory category to search",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_memory_file",
                "description": "Read a specific memory file by relative path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path within person dir",
                        },
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_memory_file",
                "description": "Write or append to a memory file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["overwrite", "append"],
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "send_message",
                "description": "Send a message to another person. The recipient will be notified immediately.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "Recipient person name",
                        },
                        "content": {
                            "type": "string",
                            "description": "Message content",
                        },
                        "reply_to": {
                            "type": "string",
                            "description": "Message ID to reply to (optional)",
                        },
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID to continue a conversation (optional)",
                        },
                    },
                    "required": ["to", "content"],
                },
            },
        ]

        # Delegate tool (for commanders with Anthropic SDK fallback / A1)
        if self._delegate_fn and self.model_config.role == "commander":
            tools.append({
                "name": "delegate_task",
                "description": "subordinate にタスクを委任し、結果を受け取る。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string", "description": "委任先の Person 名"},
                        "task": {"type": "string", "description": "実行してほしい作業の指示"},
                        "context": {"type": "string", "description": "作業に必要な背景情報（任意）"},
                    },
                    "required": ["to", "task"],
                },
            })

        # External tools from registry
        if self._tool_registry:
            try:
                import importlib
                from core.tools import TOOL_MODULES
                for tool_name in self._tool_registry:
                    if tool_name in TOOL_MODULES:
                        mod = importlib.import_module(TOOL_MODULES[tool_name])
                        if hasattr(mod, "get_tool_schemas"):
                            tools.extend(mod.get_tool_schemas())
            except Exception:
                logger.debug("Failed to load external tool schemas", exc_info=True)

        return tools

    def _handle_tool_call(self, name: str, args: dict) -> str:
        logger.debug("tool_call name=%s args_keys=%s", name, list(args.keys()))

        if name == "search_memory":
            scope = args.get("scope", "all")
            results = self.memory.search_memory_text(args.get("query", ""), scope=scope)
            logger.debug(
                "search_memory query=%s scope=%s results=%d",
                args.get("query", ""), scope, len(results),
            )
            if not results:
                return f"No results for '{args.get('query', '')}'"
            return "\n".join(
                f"- {fname}: {line}" for fname, line in results[:10]
            )

        if name == "read_memory_file":
            path = self.person_dir / args["path"]
            if path.exists() and path.is_file():
                logger.debug("read_memory_file path=%s", args["path"])
                return path.read_text(encoding="utf-8")
            logger.debug("read_memory_file NOT FOUND path=%s", args["path"])
            return f"File not found: {args['path']}"

        if name == "write_memory_file":
            path = self.person_dir / args["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if args.get("mode") == "append":
                with open(path, "a", encoding="utf-8") as f:
                    f.write(args["content"])
            else:
                path.write_text(args["content"], encoding="utf-8")
            logger.info("write_memory_file path=%s mode=%s", args["path"], args.get("mode", "overwrite"))
            return f"Written to {args['path']}"

        if name == "send_message":
            if not self.messenger:
                return "Error: messenger not configured"
            msg = self.messenger.send(
                to=args["to"],
                content=args["content"],
                thread_id=args.get("thread_id", ""),
                reply_to=args.get("reply_to", ""),
            )
            logger.info("send_message to=%s thread=%s", args["to"], msg.thread_id)
            return f"Message sent to {args['to']} (id: {msg.id}, thread: {msg.thread_id})"

        # ── File operation tools (A2) ──────────────────────
        if name == "read_file":
            return self._handle_read_file(args)

        if name == "write_file":
            return self._handle_write_file(args)

        if name == "edit_file":
            return self._handle_edit_file(args)

        if name == "execute_command":
            return self._handle_execute_command(args)

        # External tool dispatch
        if self._tool_registry:
            result = self._handle_external_tool(name, args)
            if not result.startswith("Unknown tool:"):
                return result

        logger.warning("Unknown tool requested: %s", name)
        return f"Unknown tool: {name}"

    # ── File / command tool handlers (A2) ────────────────

    def _check_file_permission(self, path: str) -> str | None:
        """Check if the file path is allowed by permissions.md.

        Returns None if allowed, or an error message string if denied.

        Access rules (evaluated in order):
          1. Own person_dir — always allowed
          2. Paths listed under ``ファイル操作`` section in permissions.md
          3. Everything else — denied
        """
        resolved = Path(path).resolve()

        # Always allow access to own person_dir
        if resolved.is_relative_to(self.person_dir.resolve()):
            return None

        permissions = self.memory.read_permissions()
        if "ファイル操作" not in permissions:
            return "Permission denied: file operations not enabled in permissions.md"

        # Parse allowed directory whitelist from permissions.md
        #   ## ファイル操作
        #   - /home/main/dev/project-x/
        #   - /tmp/workspace/
        allowed_dirs: list[Path] = []
        in_file_section = False
        for line in permissions.splitlines():
            stripped = line.strip()
            if "ファイル操作" in stripped:
                in_file_section = True
                continue
            if in_file_section and stripped.startswith("#"):
                break
            if in_file_section and stripped.startswith("-"):
                dir_path = stripped.lstrip("- ").split(":")[0].strip()
                if dir_path.startswith("/"):
                    allowed_dirs.append(Path(dir_path).resolve())

        if not allowed_dirs:
            # Section exists but no explicit paths = deny external access
            return (
                "Permission denied: no allowed paths listed under ファイル操作. "
                "Add directory paths (e.g. '- /path/to/dir/') to permissions.md."
            )

        for allowed in allowed_dirs:
            if resolved.is_relative_to(allowed):
                return None

        return (
            f"Permission denied: '{path}' is not under any allowed directory. "
            f"Allowed: {[str(d) for d in allowed_dirs]}"
        )

    # Shell metacharacters that indicate injection attempts.
    _SHELL_METACHAR_RE = re.compile(r"[;&|`$(){}]")

    def _check_command_permission(self, command: str) -> str | None:
        """Check if the command is in the allowed list from permissions.md.

        Returns None if allowed, or an error message string if denied.
        Rejects commands containing shell metacharacters to prevent injection.
        """
        if not command or not command.strip():
            return "Permission denied: empty command"

        # Reject shell metacharacters regardless of permissions
        if self._SHELL_METACHAR_RE.search(command):
            return (
                "Permission denied: command contains shell metacharacters "
                f"({self._SHELL_METACHAR_RE.pattern}). "
                "Use separate tool calls instead of chaining commands."
            )

        permissions = self.memory.read_permissions()
        if "コマンド実行" not in permissions:
            return "Permission denied: command execution not enabled in permissions.md"

        # Parse the command safely
        try:
            argv = shlex.split(command)
        except ValueError as e:
            return f"Permission denied: invalid command syntax: {e}"

        if not argv:
            return "Permission denied: empty command after parsing"

        # Extract allowed commands (lines like "- git: OK" or "- npm: OK")
        allowed: list[str] = []
        in_cmd_section = False
        for line in permissions.splitlines():
            stripped = line.strip()
            if "コマンド実行" in stripped:
                in_cmd_section = True
                continue
            if in_cmd_section and stripped.startswith("#"):
                break
            if in_cmd_section and stripped.startswith("-"):
                cmd_name = stripped.lstrip("- ").split(":")[0].strip()
                if cmd_name:
                    allowed.append(cmd_name)
        if not allowed:
            return None  # No explicit list = allow all (section exists)

        cmd_base = argv[0]
        if cmd_base not in allowed:
            return f"Permission denied: command '{cmd_base}' not in allowed list {allowed}"
        return None

    def _handle_read_file(self, args: dict) -> str:
        path_str = args.get("path", "")
        err = self._check_file_permission(path_str)
        if err:
            return err
        path = Path(path_str)
        if not path.exists():
            return f"File not found: {path_str}"
        if not path.is_file():
            return f"Not a file: {path_str}"
        try:
            content = path.read_text(encoding="utf-8")
            logger.info("read_file path=%s len=%d", path_str, len(content))
            return content[:100_000]  # cap at 100k chars
        except Exception as e:
            return f"Error reading {path_str}: {e}"

    def _handle_write_file(self, args: dict) -> str:
        path_str = args.get("path", "")
        err = self._check_file_permission(path_str)
        if err:
            return err
        path = Path(path_str)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args.get("content", ""), encoding="utf-8")
            logger.info("write_file path=%s", path_str)
            return f"Written to {path_str}"
        except Exception as e:
            return f"Error writing {path_str}: {e}"

    def _handle_edit_file(self, args: dict) -> str:
        path_str = args.get("path", "")
        err = self._check_file_permission(path_str)
        if err:
            return err
        path = Path(path_str)
        if not path.exists():
            return f"File not found: {path_str}"
        try:
            content = path.read_text(encoding="utf-8")
            old = args.get("old_string", "")
            new = args.get("new_string", "")
            if old not in content:
                return f"old_string not found in {path_str}"
            count = content.count(old)
            if count > 1:
                return f"old_string matches {count} locations — provide more context to make it unique"
            content = content.replace(old, new, 1)
            path.write_text(content, encoding="utf-8")
            logger.info("edit_file path=%s", path_str)
            return f"Edited {path_str}"
        except Exception as e:
            return f"Error editing {path_str}: {e}"

    def _handle_execute_command(self, args: dict) -> str:
        command = args.get("command", "")
        err = self._check_command_permission(command)
        if err:
            return err
        timeout = args.get("timeout", 30)
        try:
            argv = shlex.split(command)
        except ValueError as e:
            return f"Error parsing command: {e}"
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.person_dir),
            )
            output = proc.stdout
            if proc.stderr:
                output += f"\n[stderr]\n{proc.stderr}"
            logger.info(
                "execute_command cmd=%s rc=%d", command[:80], proc.returncode,
            )
            return output[:50_000] or f"(exit code {proc.returncode})"
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"

    # ── Delegate tool handler (async) ────────────────────

    # Default delegation timeout in seconds.
    _DELEGATE_TIMEOUT_S: int = 300

    async def _handle_delegate_tool_call(self, args: dict) -> str:
        """Handle the delegate_task tool call (async because it awaits subordinate).

        Enforces a timeout to prevent indefinite blocking when the
        subordinate hangs or takes excessively long.
        """
        if not self._delegate_fn:
            return "Error: delegation not configured for this person"
        target = args.get("to", "")
        task = args.get("task", "")
        context = args.get("context")
        if not target or not task:
            return "Error: 'to' and 'task' are required"
        logger.info("delegate_task to=%s task=%s", target, task[:100])
        try:
            result = await asyncio.wait_for(
                self._delegate_fn(target, task, context),
                timeout=self._DELEGATE_TIMEOUT_S,
            )
            logger.info("delegate_task completed, result_len=%d", len(result))
            return result
        except asyncio.TimeoutError:
            logger.error(
                "delegate_task timed out after %ds: to=%s",
                self._DELEGATE_TIMEOUT_S, target,
            )
            return (
                f"Delegation to '{target}' timed out after "
                f"{self._DELEGATE_TIMEOUT_S}s. The subordinate may still be "
                f"running — consider checking their status or retrying."
            )
        except Exception as e:
            logger.error("delegate_task failed: %s", e)
            return f"Delegation failed: {e}"

    def _handle_external_tool(self, name: str, args: dict) -> str:
        """Dispatch to external tool modules via direct Python calls."""
        import importlib
        import json
        from core.tools import TOOL_MODULES

        for tool_name, module_path in TOOL_MODULES.items():
            if tool_name not in self._tool_registry:
                continue
            try:
                mod = importlib.import_module(module_path)
                schemas = mod.get_tool_schemas() if hasattr(mod, "get_tool_schemas") else []
                schema_names = [s["name"] for s in schemas]
                if name not in schema_names:
                    continue

                result = self._execute_tool_function(mod, tool_name, name, args)
                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
                return str(result) if result is not None else "(no output)"
            except Exception as e:
                logger.warning("External tool %s failed: %s", name, e)
                return f"Error executing {name}: {e}"

        return f"Unknown tool: {name}"

    def _execute_tool_function(self, mod, tool_name: str, schema_name: str, args: dict):
        """Execute the appropriate function for the given tool schema name."""
        # --- web_search ---
        if schema_name == "web_search":
            return mod.search(**args)

        # --- x_search ---
        if schema_name == "x_search":
            client = mod.XSearchClient()
            return client.search_recent(
                query=args["query"],
                max_results=args.get("max_results", 10),
                days=args.get("days", 7),
            )
        if schema_name == "x_user_tweets":
            client = mod.XSearchClient()
            return client.get_user_tweets(
                username=args["username"],
                max_results=args.get("max_results", 10),
                days=args.get("days"),
            )

        # --- chatwork ---
        if schema_name == "chatwork_send":
            client = mod.ChatworkClient()
            room_id = client.resolve_room_id(args["room"])
            return client.post_message(room_id, args["message"])
        if schema_name == "chatwork_messages":
            client = mod.ChatworkClient()
            room_id = client.resolve_room_id(args["room"])
            cache = mod.MessageCache()
            try:
                msgs = client.get_messages(room_id, force=True)
                if msgs:
                    cache.upsert_messages(room_id, msgs)
                    cache.update_sync_state(room_id)
                return cache.get_recent(room_id, limit=args.get("limit", 20))
            finally:
                cache.close()
        if schema_name == "chatwork_search":
            client = mod.ChatworkClient()
            cache = mod.MessageCache()
            try:
                room_id = None
                if args.get("room"):
                    room_id = client.resolve_room_id(args["room"])
                return cache.search(
                    args["keyword"], room_id=room_id, limit=args.get("limit", 50),
                )
            finally:
                cache.close()
        if schema_name == "chatwork_unreplied":
            client = mod.ChatworkClient()
            cache = mod.MessageCache()
            try:
                my_info = client.me()
                my_id = str(my_info["account_id"])
                return cache.find_unreplied(
                    my_id, exclude_toall=not args.get("include_toall", False),
                )
            finally:
                cache.close()
        if schema_name == "chatwork_rooms":
            client = mod.ChatworkClient()
            return client.rooms()

        # --- slack ---
        if schema_name == "slack_send":
            client = mod.SlackClient()
            channel_id = client.resolve_channel(args["channel"])
            return client.post_message(
                channel_id,
                args["message"],
                thread_ts=args.get("thread_ts"),
            )
        if schema_name == "slack_messages":
            client = mod.SlackClient()
            channel_id = client.resolve_channel(args["channel"])
            cache = mod.MessageCache()
            try:
                limit = args.get("limit", 20)
                msgs = client.channel_history(channel_id, limit=limit)
                if msgs:
                    for m in msgs:
                        uid = m.get("user", m.get("bot_id", ""))
                        if uid:
                            m["user_name"] = client.resolve_user_name(uid)
                    cache.upsert_messages(channel_id, msgs)
                    cache.update_sync_state(channel_id)
                return cache.get_recent(channel_id, limit=limit)
            finally:
                cache.close()
        if schema_name == "slack_search":
            client = mod.SlackClient()
            cache = mod.MessageCache()
            try:
                channel_id = None
                if args.get("channel"):
                    channel_id = client.resolve_channel(args["channel"])
                return cache.search(
                    args["keyword"], channel_id=channel_id, limit=args.get("limit", 50),
                )
            finally:
                cache.close()
        if schema_name == "slack_unreplied":
            client = mod.SlackClient()
            cache = mod.MessageCache()
            try:
                client.auth_test()
                return cache.find_unreplied(client.my_user_id)
            finally:
                cache.close()
        if schema_name == "slack_channels":
            client = mod.SlackClient()
            return client.channels()

        # --- gmail ---
        if schema_name == "gmail_unread":
            client = mod.GmailClient()
            emails = client.get_unread_emails(max_results=args.get("max_results", 20))
            return [
                {"id": e.id, "from": e.from_addr, "subject": e.subject, "snippet": e.snippet}
                for e in emails
            ]
        if schema_name == "gmail_read_body":
            client = mod.GmailClient()
            return client.get_email_body(args["message_id"])
        if schema_name == "gmail_draft":
            client = mod.GmailClient()
            result = client.create_draft(
                to=args["to"],
                subject=args["subject"],
                body=args["body"],
                thread_id=args.get("thread_id"),
                in_reply_to=args.get("in_reply_to"),
            )
            return {"success": result.success, "draft_id": result.draft_id, "error": result.error}

        # --- local_llm ---
        if schema_name == "local_llm_generate":
            client = mod.OllamaClient(
                server=args.get("server", "auto"),
                model=args.get("model"),
                hint=args.get("hint"),
            )
            return client.generate(
                prompt=args["prompt"],
                system=args.get("system", ""),
                temperature=args.get("temperature", 0.7),
                max_tokens=args.get("max_tokens", 4096),
                think=args.get("think", "off"),
            )
        if schema_name == "local_llm_chat":
            client = mod.OllamaClient(
                server=args.get("server", "auto"),
                model=args.get("model"),
                hint=args.get("hint"),
            )
            return client.chat(
                messages=args["messages"],
                system=args.get("system", ""),
                temperature=args.get("temperature", 0.7),
                max_tokens=args.get("max_tokens", 4096),
                think=args.get("think", "off"),
            )
        if schema_name == "local_llm_models":
            client = mod.OllamaClient(server=args.get("server", "auto"))
            return client.list_models()
        if schema_name == "local_llm_status":
            client = mod.OllamaClient()
            return client.server_status()

        # --- transcribe ---
        if schema_name == "transcribe_audio":
            return mod.process_audio(
                audio_path=args["audio_path"],
                language=args.get("language"),
                model=args.get("model"),
                raw_only=args.get("raw_only", False),
                custom_prompt=args.get("custom_prompt"),
            )

        # --- aws_collector ---
        if schema_name == "aws_ecs_status":
            collector = mod.AWSCollector(region=args.get("region"))
            return collector.get_ecs_status(args["cluster"], args["service"])
        if schema_name == "aws_error_logs":
            collector = mod.AWSCollector(region=args.get("region"))
            return collector.get_error_logs(
                log_group=args["log_group"],
                hours=args.get("hours", 1),
                patterns=args.get("patterns"),
            )
        if schema_name == "aws_metrics":
            collector = mod.AWSCollector(region=args.get("region"))
            return collector.get_metrics(
                cluster=args["cluster"],
                service=args["service"],
                metric=args.get("metric", "CPUUtilization"),
                hours=args.get("hours", 1),
            )

        # --- github ---
        if schema_name == "github_list_issues":
            client = mod.GitHubClient(repo=args.get("repo"))
            return client.list_issues(
                state=args.get("state", "open"),
                labels=args.get("labels"),
                limit=args.get("limit", 20),
            )
        if schema_name == "github_create_issue":
            client = mod.GitHubClient(repo=args.get("repo"))
            return client.create_issue(
                title=args["title"],
                body=args.get("body", ""),
                labels=args.get("labels"),
            )
        if schema_name == "github_list_prs":
            client = mod.GitHubClient(repo=args.get("repo"))
            return client.list_prs(
                state=args.get("state", "open"),
                limit=args.get("limit", 20),
            )
        if schema_name == "github_create_pr":
            client = mod.GitHubClient(repo=args.get("repo"))
            return client.create_pr(
                title=args["title"],
                body=args.get("body", ""),
                head=args["head"],
                base=args.get("base", "main"),
                draft=args.get("draft", False),
            )

        raise ValueError(f"No handler for tool schema: {schema_name}")
