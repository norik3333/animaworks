from __future__ import annotations

"""Tests for per-thread stream parallelization.

Phase 1: ShortTermMemory thread_id path separation
Phase 2: per-thread locks, interrupt events, status slots
Phase 3: codex_thread_id / agent SDK session path separation
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Phase 1: ShortTermMemory thread_id ───────────────────────


class TestShortTermMemoryThreadId:
    """ShortTermMemory creates separate directories per thread_id."""

    def test_default_thread_uses_existing_path(self, tmp_path: Path) -> None:
        from core.memory.shortterm import ShortTermMemory

        stm = ShortTermMemory(tmp_path, session_type="chat", thread_id="default")
        assert stm.shortterm_dir == tmp_path / "shortterm" / "chat"
        assert stm.shortterm_dir.exists()

    def test_custom_thread_creates_subdirectory(self, tmp_path: Path) -> None:
        from core.memory.shortterm import ShortTermMemory

        stm = ShortTermMemory(tmp_path, session_type="chat", thread_id="thread-abc")
        assert stm.shortterm_dir == tmp_path / "shortterm" / "chat" / "thread-abc"
        assert stm.shortterm_dir.exists()

    def test_different_threads_are_isolated(self, tmp_path: Path) -> None:
        from core.memory.shortterm import ShortTermMemory, SessionState

        stm_a = ShortTermMemory(tmp_path, thread_id="thread-a")
        stm_b = ShortTermMemory(tmp_path, thread_id="thread-b")

        stm_a.save(SessionState(session_id="a", trigger="test"))
        assert stm_a.has_pending()
        assert not stm_b.has_pending()

        stm_b.save(SessionState(session_id="b", trigger="test"))
        assert stm_b.has_pending()

        loaded_a = stm_a.load()
        loaded_b = stm_b.load()
        assert loaded_a is not None and loaded_a.session_id == "a"
        assert loaded_b is not None and loaded_b.session_id == "b"

    def test_default_thread_omitted_is_backward_compatible(self, tmp_path: Path) -> None:
        from core.memory.shortterm import ShortTermMemory

        stm_no_arg = ShortTermMemory(tmp_path)
        stm_explicit = ShortTermMemory(tmp_path, thread_id="default")
        assert stm_no_arg.shortterm_dir == stm_explicit.shortterm_dir

    def test_heartbeat_session_type_unaffected(self, tmp_path: Path) -> None:
        from core.memory.shortterm import ShortTermMemory

        stm = ShortTermMemory(tmp_path, session_type="heartbeat", thread_id="default")
        assert stm.shortterm_dir == tmp_path / "shortterm" / "heartbeat"


# ── Phase 2: Per-thread locks, interrupts, status ────────────


class TestPerThreadAgentLock:
    """AgentCore._get_agent_lock returns independent locks per thread."""

    def test_same_thread_returns_same_lock(self) -> None:
        from core.agent import AgentCore

        agent = MagicMock(spec=AgentCore)
        agent._agent_locks = {}
        agent._MAX_AGENT_LOCKS = 20

        lock1 = AgentCore._get_agent_lock(agent, "t1")
        lock2 = AgentCore._get_agent_lock(agent, "t1")
        assert lock1 is lock2

    def test_different_threads_return_different_locks(self) -> None:
        from core.agent import AgentCore

        agent = MagicMock(spec=AgentCore)
        agent._agent_locks = {}
        agent._MAX_AGENT_LOCKS = 20

        lock_a = AgentCore._get_agent_lock(agent, "a")
        lock_b = AgentCore._get_agent_lock(agent, "b")
        assert lock_a is not lock_b

    def test_lru_eviction_when_max_reached(self) -> None:
        from core.agent import AgentCore

        agent = MagicMock(spec=AgentCore)
        agent._agent_locks = {}
        agent._MAX_AGENT_LOCKS = 3

        AgentCore._get_agent_lock(agent, "t1")
        AgentCore._get_agent_lock(agent, "t2")
        AgentCore._get_agent_lock(agent, "t3")
        assert len(agent._agent_locks) == 3

        AgentCore._get_agent_lock(agent, "t4")
        assert len(agent._agent_locks) <= 3
        assert "t4" in agent._agent_locks


class TestPerThreadInterruptEvent:
    """DigitalAnima._get_interrupt_event and interrupt() per-thread behavior."""

    def _make_anima_mock(self):
        from core.anima import DigitalAnima

        anima = MagicMock(spec=DigitalAnima)
        anima._interrupt_events = {}
        anima.name = "test"
        return anima

    def test_same_thread_returns_same_event(self) -> None:
        from core.anima import DigitalAnima

        anima = self._make_anima_mock()
        e1 = DigitalAnima._get_interrupt_event(anima, "t1")
        e2 = DigitalAnima._get_interrupt_event(anima, "t1")
        assert e1 is e2

    def test_different_threads_return_different_events(self) -> None:
        from core.anima import DigitalAnima

        anima = self._make_anima_mock()
        e_a = DigitalAnima._get_interrupt_event(anima, "a")
        e_b = DigitalAnima._get_interrupt_event(anima, "b")
        assert e_a is not e_b

    @pytest.mark.asyncio
    async def test_interrupt_all_threads(self) -> None:
        from core.anima import DigitalAnima

        anima = self._make_anima_mock()
        e_a = DigitalAnima._get_interrupt_event(anima, "a")
        e_b = DigitalAnima._get_interrupt_event(anima, "b")

        assert not e_a.is_set()
        assert not e_b.is_set()

        await DigitalAnima.interrupt(anima, thread_id=None)
        assert e_a.is_set()
        assert e_b.is_set()

    @pytest.mark.asyncio
    async def test_interrupt_specific_thread(self) -> None:
        from core.anima import DigitalAnima

        anima = self._make_anima_mock()
        e_a = DigitalAnima._get_interrupt_event(anima, "a")
        e_b = DigitalAnima._get_interrupt_event(anima, "b")

        await DigitalAnima.interrupt(anima, thread_id="a")
        assert e_a.is_set()
        assert not e_b.is_set()


class TestStatusSlotsCompoundKey:
    """_status_slots uses conversation:{thread_id} compound keys."""

    @patch("core.anima.AgentCore")
    @patch("core.anima.Messenger")
    @patch("core.anima.MemoryManager")
    def test_primary_status_from_conversation_slots(
        self, mock_mm, mock_msg, mock_agent, tmp_path: Path
    ) -> None:
        from core.anima import DigitalAnima

        mock_mm.return_value.read_model_config.return_value = MagicMock()
        mock_agent.return_value = MagicMock()
        mock_agent.return_value.background_manager = None
        mock_agent.return_value._tool_handler = MagicMock()

        shared = tmp_path / "shared"
        shared.mkdir()
        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)

        dp = DigitalAnima(anima_dir, shared)

        # No conversation slots → fallback to inbox/background
        assert dp.primary_status == "idle"

        # Set a conversation slot
        dp._status_slots["conversation:t1"] = "thinking"
        assert dp.primary_status == "thinking"

        # Multiple conversation slots — first non-idle wins
        dp._status_slots["conversation:t2"] = "idle"
        assert dp.primary_status == "thinking"

        # Clear t1
        dp._status_slots["conversation:t1"] = "idle"
        assert dp.primary_status == "idle"

    @patch("core.anima.AgentCore")
    @patch("core.anima.Messenger")
    @patch("core.anima.MemoryManager")
    def test_primary_task_from_conversation_slots(
        self, mock_mm, mock_msg, mock_agent, tmp_path: Path
    ) -> None:
        from core.anima import DigitalAnima

        mock_mm.return_value.read_model_config.return_value = MagicMock()
        mock_agent.return_value = MagicMock()
        mock_agent.return_value.background_manager = None
        mock_agent.return_value._tool_handler = MagicMock()

        shared = tmp_path / "shared"
        shared.mkdir()
        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)

        dp = DigitalAnima(anima_dir, shared)

        assert dp.primary_task == ""

        dp._task_slots["conversation:t1"] = "Responding to user"
        assert dp.primary_task == "Responding to user"

        dp._task_slots["conversation:t1"] = ""
        assert dp.primary_task == ""


# ── Phase 3: codex_thread_id / SDK session path separation ───


class TestCodexThreadIdPath:
    """codex_thread_id paths are separated per chat thread_id."""

    def test_default_thread_uses_existing_path(self, tmp_path: Path) -> None:
        from core.execution.codex_sdk import _thread_id_path

        p = _thread_id_path(tmp_path, "chat", "default")
        assert p == tmp_path / "shortterm" / "chat" / "codex_thread_id.txt"

    def test_custom_thread_uses_subdirectory(self, tmp_path: Path) -> None:
        from core.execution.codex_sdk import _thread_id_path

        p = _thread_id_path(tmp_path, "chat", "thread-xyz")
        assert p == tmp_path / "shortterm" / "chat" / "thread-xyz" / "codex_thread_id.txt"

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        from core.execution.codex_sdk import _save_thread_id, _load_thread_id

        _save_thread_id(tmp_path, "tid-123", "chat", "my-thread")
        loaded = _load_thread_id(tmp_path, "chat", "my-thread")
        assert loaded == "tid-123"

        # Different thread should be None
        assert _load_thread_id(tmp_path, "chat", "other") is None


class TestSDKSessionIdPath:
    """Agent SDK session IDs are separated per thread_id."""

    def test_default_thread_uses_existing_filename(self) -> None:
        from core.execution._sdk_session import _session_file

        assert _session_file("chat", "default") == "current_session_chat.json"

    def test_custom_thread_includes_thread_id(self) -> None:
        from core.execution._sdk_session import _session_file

        assert _session_file("chat", "thread-1") == "current_session_chat_thread-1.json"

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        from core.execution._sdk_session import _save_session_id, _load_session_id

        state_dir = tmp_path / "state"
        state_dir.mkdir()

        _save_session_id(tmp_path, "sess-abc", "chat", "my-thread")
        loaded = _load_session_id(tmp_path, "chat", "my-thread")
        assert loaded == "sess-abc"

        assert _load_session_id(tmp_path, "chat", "default") is None
