# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for LLM API retry — async_retry_with_backoff, num_retries
propagation to LiteLLM kwargs, and Anthropic SDK retry wrapping.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools._retry import async_retry_with_backoff


# ── async_retry_with_backoff ──────────────────────────────────


class _TransientError(Exception):
    pass


class _PermanentError(Exception):
    pass


@pytest.mark.asyncio
async def test_async_retry_succeeds_first_attempt():
    fn = AsyncMock(return_value="ok")
    result = await async_retry_with_backoff(
        fn, max_retries=3, retry_on=(_TransientError,),
    )
    assert result == "ok"
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_succeeds_after_transient_failures():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _TransientError("boom")
        return "recovered"

    result = await async_retry_with_backoff(
        flaky,
        max_retries=3,
        base_delay=0.01,
        retry_on=(_TransientError,),
    )
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_retry_raises_after_exhaustion():
    fn = AsyncMock(side_effect=_TransientError("always fails"))
    with pytest.raises(_TransientError, match="always fails"):
        await async_retry_with_backoff(
            fn, max_retries=2, base_delay=0.01, retry_on=(_TransientError,),
        )
    assert fn.await_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_async_retry_does_not_catch_unrelated_exceptions():
    fn = AsyncMock(side_effect=_PermanentError("fatal"))
    with pytest.raises(_PermanentError, match="fatal"):
        await async_retry_with_backoff(
            fn, max_retries=3, base_delay=0.01, retry_on=(_TransientError,),
        )
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_zero_retries():
    fn = AsyncMock(side_effect=_TransientError("once"))
    with pytest.raises(_TransientError):
        await async_retry_with_backoff(
            fn, max_retries=0, retry_on=(_TransientError,),
        )
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_strips_retry_params_from_fn_kwargs():
    """Retry-control kwargs must not leak into the wrapped function."""
    received_kwargs: dict = {}

    async def capture(**kwargs):
        received_kwargs.update(kwargs)
        return "ok"

    result = await async_retry_with_backoff(
        capture,
        max_retries=2,
        base_delay=0.01,
        max_delay=5.0,
        retry_on=(_TransientError,),
        model="test-model",
        temperature=0.7,
    )
    assert result == "ok"
    assert "model" in received_kwargs
    assert "temperature" in received_kwargs
    assert "max_retries" not in received_kwargs
    assert "base_delay" not in received_kwargs
    assert "retry_on" not in received_kwargs


@pytest.mark.asyncio
async def test_async_retry_respects_max_delay():
    delays: list[float] = []
    _orig_sleep = asyncio.sleep

    async def _capture_sleep(t):
        delays.append(t)

    fn = AsyncMock(side_effect=_TransientError("fail"))

    with patch("core.tools._retry.asyncio.sleep", side_effect=_capture_sleep):
        with pytest.raises(_TransientError):
            await async_retry_with_backoff(
                fn,
                max_retries=5,
                base_delay=1.0,
                max_delay=4.0,
                retry_on=(_TransientError,),
            )

    assert all(d <= 4.0 for d in delays)
    assert len(delays) == 5


# ── _build_llm_kwargs num_retries propagation ─────────────────


def _make_context_mixin():
    """Create a minimal ContextMixin instance for testing."""
    from core.execution._litellm_context import ContextMixin

    class FakeExecutor(ContextMixin):
        def __init__(self):
            self._model_config = MagicMock()
            self._model_config.model = "openai/gpt-4o"
            self._model_config.max_tokens = 4096
            self._model_config.thinking = None
            self._model_config.api_base_url = None
            self._model_config.llm_timeout = 60
            self._model_config.credential = None
            self._model_config.thinking_effort = None

        def _resolve_api_key(self):
            return None

        def _resolve_llm_timeout(self):
            return 60

        def _resolve_num_retries(self):
            return 5

        def _apply_provider_kwargs(self, kwargs):
            pass

    return FakeExecutor()


def test_build_llm_kwargs_includes_num_retries():
    """_build_llm_kwargs() should include the num_retries key."""
    executor = _make_context_mixin()
    kwargs = executor._build_llm_kwargs()
    assert "num_retries" in kwargs
    assert kwargs["num_retries"] == 5


# ── _resolve_num_retries on BaseExecutor ──────────────────────


def test_resolve_num_retries_from_config():
    """_resolve_num_retries reads from config.server.llm_num_retries."""
    from core.execution.base import BaseExecutor

    mock_config = MagicMock()
    mock_config.server.llm_num_retries = 7

    model_config = MagicMock()
    model_config.model = "claude-sonnet-4-6"

    with patch("core.config.load_config", return_value=mock_config):
        with patch.multiple(BaseExecutor, __abstractmethods__=frozenset()):
            executor = BaseExecutor.__new__(BaseExecutor)
            executor._model_config = model_config
            executor._anima_dir = Path("/tmp/test")
            assert executor._resolve_num_retries() == 7


def test_resolve_num_retries_default_on_error():
    """_resolve_num_retries falls back to 3 when config loading fails."""
    from core.execution.base import BaseExecutor

    model_config = MagicMock()
    model_config.model = "claude-sonnet-4-6"

    with patch("core.config.load_config", side_effect=RuntimeError("no config")):
        with patch.multiple(BaseExecutor, __abstractmethods__=frozenset()):
            executor = BaseExecutor.__new__(BaseExecutor)
            executor._model_config = model_config
            executor._anima_dir = Path("/tmp/test")
            assert executor._resolve_num_retries() == 3


# ── ServerConfig.llm_num_retries ──────────────────────────────


def test_server_config_llm_num_retries_default():
    from core.config.models import ServerConfig

    cfg = ServerConfig()
    assert cfg.llm_num_retries == 3


def test_server_config_llm_num_retries_custom():
    from core.config.models import ServerConfig

    cfg = ServerConfig(llm_num_retries=10)
    assert cfg.llm_num_retries == 10


# ── Anthropic non-streaming retry ─────────────────────────────


@pytest.mark.asyncio
async def test_anthropic_non_streaming_retries_on_rate_limit():
    """AnthropicFallbackExecutor.execute retries on RateLimitError."""

    class FakeRateLimitError(Exception):
        pass

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise FakeRateLimitError("429 Too Many Requests")
        response = MagicMock()
        response.content = [MagicMock(type="text", text="hello")]
        response.usage = MagicMock(input_tokens=100, output_tokens=50)
        response.stop_reason = "end_turn"
        return response

    with patch("core.tools._retry.asyncio.sleep", new_callable=AsyncMock):
        result = await async_retry_with_backoff(
            fake_create,
            model="test",
            max_retries=3,
            base_delay=0.01,
            retry_on=(FakeRateLimitError,),
        )
    assert result.content[0].text == "hello"
    assert call_count == 3


# ── _stream_with_retry ────────────────────────────────────────


class _FakeTransientAPIError(Exception):
    """Simulates a transient Anthropic API error for stream retry tests."""
    pass


@pytest.mark.asyncio
async def test_stream_with_retry_succeeds_after_failures():
    """_stream_with_retry retries stream connection on transient errors."""
    from core.execution.anthropic_fallback import _stream_with_retry

    call_count = 0

    class FakeStreamCM:
        async def __aenter__(self):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _FakeTransientAPIError("connection reset")
            return self

        async def __aexit__(self, *args):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    client = MagicMock()
    client.messages.stream = MagicMock(return_value=FakeStreamCM())

    with patch("core.execution.anthropic_fallback.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "core.execution.anthropic_fallback._anthropic_retryable_errors",
            return_value=(_FakeTransientAPIError,),
        ):
            async with _stream_with_retry(client, {}, max_retries=3) as stream:
                events = [e async for e in stream]

    assert call_count == 2
    assert events == []


@pytest.mark.asyncio
async def test_stream_with_retry_raises_after_max_retries():
    """_stream_with_retry raises after exhausting retries."""
    from core.execution.anthropic_fallback import _stream_with_retry

    class FakeStreamCM:
        async def __aenter__(self):
            raise _FakeTransientAPIError("429")

        async def __aexit__(self, *args):
            pass

    client = MagicMock()
    client.messages.stream = MagicMock(return_value=FakeStreamCM())

    with patch("core.execution.anthropic_fallback.asyncio.sleep", new_callable=AsyncMock):
        with patch(
            "core.execution.anthropic_fallback._anthropic_retryable_errors",
            return_value=(_FakeTransientAPIError,),
        ):
            with pytest.raises(_FakeTransientAPIError):
                async with _stream_with_retry(client, {}, max_retries=2) as stream:
                    pass
