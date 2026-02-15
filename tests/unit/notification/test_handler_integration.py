"""Tests for notify_human integration in ToolHandler."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.notification.notifier import HumanNotifier, NotificationChannel
from core.tooling.handler import ToolHandler


# ── Mock Channel ──────────────────────────────────────────────


class StubChannel(NotificationChannel):
    """A stub channel that records calls."""

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__({})
        self._fail = fail
        self.calls: list[dict[str, str]] = []

    @property
    def channel_type(self) -> str:
        return "stub"

    async def send(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        person_name: str = "",
    ) -> str:
        if self._fail:
            raise RuntimeError("stub failure")
        self.calls.append({
            "subject": subject,
            "body": body,
            "priority": priority,
            "person_name": person_name,
        })
        return "stub: OK"


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def person_dir(tmp_path: Path) -> Path:
    d = tmp_path / "persons" / "test-person"
    d.mkdir(parents=True)
    (d / "permissions.md").write_text("", encoding="utf-8")
    return d


@pytest.fixture
def memory() -> MagicMock:
    m = MagicMock()
    m.read_permissions.return_value = ""
    return m


@pytest.fixture
def stub_channel() -> StubChannel:
    return StubChannel()


@pytest.fixture
def notifier(stub_channel: StubChannel) -> HumanNotifier:
    return HumanNotifier([stub_channel])


@pytest.fixture
def handler_with_notifier(
    person_dir: Path, memory: MagicMock, notifier: HumanNotifier,
) -> ToolHandler:
    return ToolHandler(
        person_dir=person_dir,
        memory=memory,
        human_notifier=notifier,
    )


@pytest.fixture
def handler_without_notifier(
    person_dir: Path, memory: MagicMock,
) -> ToolHandler:
    return ToolHandler(
        person_dir=person_dir,
        memory=memory,
    )


# ── Tests ─────────────────────────────────────────────────────


class TestNotifyHumanHandler:
    def test_notify_human_success(
        self, handler_with_notifier: ToolHandler, stub_channel: StubChannel,
    ):
        result = handler_with_notifier.handle("notify_human", {
            "subject": "Test Alert",
            "body": "Something happened",
            "priority": "high",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert "stub: OK" in parsed["results"]
        assert len(stub_channel.calls) == 1
        assert stub_channel.calls[0]["subject"] == "Test Alert"
        assert stub_channel.calls[0]["priority"] == "high"
        assert stub_channel.calls[0]["person_name"] == "test-person"

    def test_notify_human_default_priority(
        self, handler_with_notifier: ToolHandler, stub_channel: StubChannel,
    ):
        result = handler_with_notifier.handle("notify_human", {
            "subject": "Info",
            "body": "FYI",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert stub_channel.calls[0]["priority"] == "normal"

    def test_notify_human_no_notifier(
        self, handler_without_notifier: ToolHandler,
    ):
        result = handler_without_notifier.handle("notify_human", {
            "subject": "Test",
            "body": "Body",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "NotConfigured"

    def test_notify_human_no_channels(
        self, person_dir: Path, memory: MagicMock,
    ):
        empty_notifier = HumanNotifier([])
        handler = ToolHandler(
            person_dir=person_dir,
            memory=memory,
            human_notifier=empty_notifier,
        )
        result = handler.handle("notify_human", {
            "subject": "Test",
            "body": "Body",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "NotConfigured"

    def test_notify_human_missing_subject(
        self, handler_with_notifier: ToolHandler,
    ):
        result = handler_with_notifier.handle("notify_human", {
            "body": "Body only",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "InvalidArguments"

    def test_notify_human_missing_body(
        self, handler_with_notifier: ToolHandler,
    ):
        result = handler_with_notifier.handle("notify_human", {
            "subject": "Subject only",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["error_type"] == "InvalidArguments"

    def test_notify_human_channel_partial_failure(
        self, person_dir: Path, memory: MagicMock,
    ):
        ok_ch = StubChannel()
        fail_ch = StubChannel(fail=True)
        notifier = HumanNotifier([ok_ch, fail_ch])
        handler = ToolHandler(
            person_dir=person_dir,
            memory=memory,
            human_notifier=notifier,
        )
        result = handler.handle("notify_human", {
            "subject": "Test",
            "body": "Body",
        })
        parsed = json.loads(result)
        assert parsed["status"] == "sent"
        assert any("OK" in r for r in parsed["results"])
        assert any("ERROR" in r for r in parsed["results"])
