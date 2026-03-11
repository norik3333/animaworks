"""Tests for streaming_handler.py abort state handling.

Verifies that session IDs are PRESERVED and only clear_checkpoint is
called in all three error paths inside _stream_producer():
  - done=False: stream ends without cycle_done
  - TimeoutError: timeout during streaming
  - Exception: general error during streaming
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.supervisor.ipc import IPCRequest
from core.supervisor.streaming_handler import StreamingIPCHandler


# ── Helpers ───────────────────────────────────────────────────


def _make_handler(anima_dir: Path) -> StreamingIPCHandler:
    """Create a StreamingIPCHandler with a mock anima."""
    mock_anima = MagicMock()
    mock_anima.needs_bootstrap = False
    return StreamingIPCHandler(
        anima=mock_anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
    )


def _make_request(message: str = "test") -> IPCRequest:
    return IPCRequest(
        id="req-1",
        method="process_message",
        params={"message": message, "stream": True},
    )


# ── done=False path (stream ends without cycle_done) ──────────


class TestSessionPreservedOnDoneFalse:
    """_stream_producer ends without cycle_done: session ID preserved, only checkpoint cleared."""

    @pytest.mark.asyncio
    async def test_session_id_not_cleared_on_stream_abort(self, tmp_path: Path) -> None:
        """_clear_session_id is NOT called when stream ends without cycle_done
        (session is preserved for next resume)."""
        handler = _make_handler(tmp_path)

        async def mock_stream_no_cycle_done(*args, **kwargs):
            yield {"type": "text_delta", "text": "partial"}

        handler._anima.process_message_stream = mock_stream_no_cycle_done

        clear_calls: list[tuple] = []

        def fake_clear_session_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
            clear_calls.append((anima_dir, session_type))

        with (
            patch("core.config.load_config") as mock_config,
            patch(
                "core.execution._sdk_session._clear_session_id",
                side_effect=fake_clear_session_id,
            ),
            patch("core.memory.shortterm.ShortTermMemory") as mock_stm_class,
        ):
            mock_config.return_value.server.keepalive_interval = 30
            mock_stm_instance = MagicMock()
            mock_stm_class.return_value = mock_stm_instance

            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert clear_calls == [], f"Expected NO session ID clears (session preserved), but got: {clear_calls}"

    @pytest.mark.asyncio
    async def test_clear_checkpoint_called_on_stream_abort(self, tmp_path: Path) -> None:
        """ShortTermMemory.clear_checkpoint() called when stream ends without
        cycle_done."""
        handler = _make_handler(tmp_path)

        async def mock_stream_no_cycle_done(*args, **kwargs):
            yield {"type": "text_delta", "text": "partial"}

        handler._anima.process_message_stream = mock_stream_no_cycle_done

        checkpoint_cleared = []

        def fake_clear_checkpoint(self_stm) -> None:
            checkpoint_cleared.append(True)

        with (
            patch("core.config.load_config") as mock_config,
            patch.object(
                __import__("core.memory.shortterm", fromlist=["ShortTermMemory"]).ShortTermMemory,
                "clear_checkpoint",
                fake_clear_checkpoint,
            ),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert len(checkpoint_cleared) >= 1, "clear_checkpoint() was not called on stream abort"

    @pytest.mark.asyncio
    async def test_done_response_still_emitted_on_stream_abort(self, tmp_path: Path) -> None:
        """A done=True IPCResponse is still yielded even after stream abort."""
        handler = _make_handler(tmp_path)

        async def mock_stream_abort(*args, **kwargs):
            yield {"type": "text_delta", "text": "hello"}

        handler._anima.process_message_stream = mock_stream_abort

        with (
            patch("core.config.load_config") as mock_config,
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        done_responses = [r for r in responses if r.done]
        assert len(done_responses) == 1, "Expected one done response after stream abort"


# ── TimeoutError path ─────────────────────────────────────────


class TestSessionPreservedOnTimeoutError:
    """TimeoutError in _stream_producer: session IDs preserved, only checkpoint cleared."""

    @pytest.mark.asyncio
    async def test_session_id_not_cleared_on_timeout(self, tmp_path: Path) -> None:
        """_clear_session_id is NOT called on TimeoutError (session preserved)."""
        handler = _make_handler(tmp_path)

        async def mock_stream_timeout(*args, **kwargs):
            raise TimeoutError("stream timeout")
            yield  # make it an async generator

        handler._anima.process_message_stream = mock_stream_timeout

        clear_calls: list[tuple] = []

        def fake_clear_session_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
            clear_calls.append((anima_dir, session_type))

        with (
            patch("core.config.load_config") as mock_config,
            patch(
                "core.execution._sdk_session._clear_session_id",
                side_effect=fake_clear_session_id,
            ),
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert clear_calls == [], f"Expected NO session ID clears on timeout, but got: {clear_calls}"

    @pytest.mark.asyncio
    async def test_ipc_timeout_error_returned_on_timeout(self, tmp_path: Path) -> None:
        """An IPC_TIMEOUT error response is yielded on TimeoutError."""
        handler = _make_handler(tmp_path)

        async def mock_stream_timeout(*args, **kwargs):
            raise TimeoutError("connection lost")
            yield

        handler._anima.process_message_stream = mock_stream_timeout

        with (
            patch("core.config.load_config") as mock_config,
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        error_responses = [r for r in responses if r.error]
        assert len(error_responses) == 1
        assert error_responses[0].error["code"] == "IPC_TIMEOUT"


# ── Exception path ────────────────────────────────────────────


class TestSessionPreservedOnException:
    """General Exception in _stream_producer: session IDs preserved, only checkpoint cleared."""

    @pytest.mark.asyncio
    async def test_session_id_not_cleared_on_general_exception(self, tmp_path: Path) -> None:
        """_clear_session_id is NOT called on general Exception (session preserved)."""
        handler = _make_handler(tmp_path)

        async def mock_stream_raises(*args, **kwargs):
            raise RuntimeError("unexpected error")
            yield

        handler._anima.process_message_stream = mock_stream_raises

        clear_calls: list[tuple] = []

        def fake_clear_session_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
            clear_calls.append((anima_dir, session_type))

        with (
            patch("core.config.load_config") as mock_config,
            patch(
                "core.execution._sdk_session._clear_session_id",
                side_effect=fake_clear_session_id,
            ),
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert clear_calls == [], f"Expected NO session ID clears on exception, but got: {clear_calls}"

    @pytest.mark.asyncio
    async def test_stream_error_returned_on_general_exception(self, tmp_path: Path) -> None:
        """A STREAM_ERROR error response is yielded on RuntimeError."""
        handler = _make_handler(tmp_path)

        async def mock_stream_raises(*args, **kwargs):
            raise RuntimeError("bad state")
            yield

        handler._anima.process_message_stream = mock_stream_raises

        with (
            patch("core.config.load_config") as mock_config,
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        error_responses = [r for r in responses if r.error]
        assert len(error_responses) == 1
        assert error_responses[0].error["code"] == "STREAM_ERROR"

    @pytest.mark.asyncio
    async def test_clear_checkpoint_called_on_general_exception(self, tmp_path: Path) -> None:
        """ShortTermMemory.clear_checkpoint() called on general Exception."""
        handler = _make_handler(tmp_path)

        async def mock_stream_raises(*args, **kwargs):
            raise ValueError("bad value")
            yield

        handler._anima.process_message_stream = mock_stream_raises

        checkpoint_cleared = []

        def fake_clear_checkpoint(self_stm) -> None:
            checkpoint_cleared.append(True)

        with (
            patch("core.config.load_config") as mock_config,
            patch.object(
                __import__("core.memory.shortterm", fromlist=["ShortTermMemory"]).ShortTermMemory,
                "clear_checkpoint",
                fake_clear_checkpoint,
            ),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert len(checkpoint_cleared) >= 1


# ── Normal success path: no unnecessary clear ─────────────────


class TestNoSessionClearOnSuccess:
    """Normal execution with cycle_done: session IDs should NOT be cleared."""

    @pytest.mark.asyncio
    async def test_no_clear_on_successful_cycle(self, tmp_path: Path) -> None:
        """_clear_session_id is NOT called when stream ends normally with cycle_done."""
        handler = _make_handler(tmp_path)

        async def mock_stream_success(*args, **kwargs):
            yield {"type": "text_delta", "text": "Hello"}
            yield {"type": "cycle_done", "cycle_result": {"summary": "Hello"}}

        handler._anima.process_message_stream = mock_stream_success

        clear_calls: list[tuple] = []

        def fake_clear_session_id(anima_dir: Path, session_type: str, thread_id: str = "default") -> None:
            clear_calls.append((anima_dir, session_type))

        with (
            patch("core.config.load_config") as mock_config,
            patch(
                "core.execution._sdk_session._clear_session_id",
                side_effect=fake_clear_session_id,
            ),
            patch("core.memory.shortterm.ShortTermMemory"),
        ):
            mock_config.return_value.server.keepalive_interval = 30
            responses = []
            async for resp in handler.handle_stream(_make_request()):
                responses.append(resp)

        assert clear_calls == [], f"Expected no session ID clears on successful stream, but got: {clear_calls}"
