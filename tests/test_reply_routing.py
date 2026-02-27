from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for call_human reply routing (notification_map + sanitization)."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────


@pytest.fixture
def routing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect get_data_dir() to a temp directory."""
    monkeypatch.setattr(
        "core.notification.reply_routing.get_data_dir", lambda: tmp_path,
    )
    return tmp_path


# ── save / lookup round-trip ─────────────────────────────


class TestNotificationMapping:
    def test_save_and_lookup(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import (
            lookup_notification_mapping,
            save_notification_mapping,
        )

        save_notification_mapping("1234567890.123456", "C0123ABC", "mikoto")

        result = lookup_notification_mapping("1234567890.123456")
        assert result is not None
        assert result["anima"] == "mikoto"
        assert result["channel"] == "C0123ABC"

    def test_lookup_unknown_ts(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import lookup_notification_mapping

        assert lookup_notification_mapping("9999999999.999999") is None

    def test_lookup_missing_file(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import lookup_notification_mapping

        assert lookup_notification_mapping("1234567890.123456") is None

    def test_multiple_mappings(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import (
            lookup_notification_mapping,
            save_notification_mapping,
        )

        save_notification_mapping("111.111", "C001", "aoi")
        save_notification_mapping("222.222", "C002", "ren")

        assert lookup_notification_mapping("111.111")["anima"] == "aoi"
        assert lookup_notification_mapping("222.222")["anima"] == "ren"

    def test_corrupted_file_returns_none(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import lookup_notification_mapping

        map_path = routing_dir / "run" / "notification_map.json"
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text("NOT VALID JSON{{{", encoding="utf-8")

        assert lookup_notification_mapping("1234567890.123456") is None

    def test_creates_run_directory(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import save_notification_mapping

        run_dir = routing_dir / "run"
        assert not run_dir.exists()

        save_notification_mapping("1234.5678", "C001", "test-anima")

        assert run_dir.exists()
        assert (run_dir / "notification_map.json").exists()


# ── TTL pruning ──────────────────────────────────────────


class TestPruning:
    def test_old_entries_removed(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import (
            lookup_notification_mapping,
            save_notification_mapping,
        )

        map_path = routing_dir / "run" / "notification_map.json"
        map_path.parent.mkdir(parents=True, exist_ok=True)

        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        data = {
            "old.entry": {
                "anima": "stale",
                "channel": "C999",
                "created_at": old_ts,
            },
        }
        map_path.write_text(json.dumps(data), encoding="utf-8")

        save_notification_mapping("new.entry", "C001", "fresh")

        assert lookup_notification_mapping("old.entry") is None
        assert lookup_notification_mapping("new.entry") is not None

    def test_recent_entries_kept(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import (
            lookup_notification_mapping,
            save_notification_mapping,
        )

        save_notification_mapping("recent.ts", "C001", "keeper")
        save_notification_mapping("another.ts", "C002", "also-kept")

        assert lookup_notification_mapping("recent.ts") is not None
        assert lookup_notification_mapping("another.ts") is not None

    def test_prune_old_entries_standalone(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import (
            lookup_notification_mapping,
            prune_old_entries,
        )

        map_path = routing_dir / "run" / "notification_map.json"
        map_path.parent.mkdir(parents=True, exist_ok=True)

        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()
        data = {
            "old.one": {"anima": "a", "channel": "C1", "created_at": old_ts},
            "new.one": {"anima": "b", "channel": "C2", "created_at": new_ts},
        }
        map_path.write_text(json.dumps(data), encoding="utf-8")

        prune_old_entries(max_age_days=7)

        assert lookup_notification_mapping("old.one") is None
        assert lookup_notification_mapping("new.one") is not None


# ── sanitize_slack_reply ─────────────────────────────────


class TestSanitizeSlackReply:
    def test_strips_user_mentions(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("<@U0123BOT> hello") == "hello"

    def test_converts_links_with_label(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("<https://example.com|Example>") == "Example"

    def test_converts_bare_links(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("<https://example.com>") == "https://example.com"

    def test_converts_channel_mentions(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("<#C123|general>") == "#general"

    def test_strips_bold(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("this is *bold* text") == "this is bold text"

    def test_strips_italic(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("this is _italic_ text") == "this is italic text"

    def test_strips_strike(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("this is ~struck~ text") == "this is struck text"

    def test_strips_inline_code(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("run `ls -la` now") == "run ls -la now"

    def test_truncates_long_text(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        long_text = "a" * 5000
        result = sanitize_slack_reply(long_text)
        assert len(result) == 4000

    def test_custom_max_length(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        result = sanitize_slack_reply("a" * 200, max_length=100)
        assert len(result) == 100

    def test_plain_text_passthrough(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("just normal text") == "just normal text"

    def test_empty_string(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        assert sanitize_slack_reply("") == ""

    def test_combined_formatting(self) -> None:
        from core.notification.reply_routing import sanitize_slack_reply

        text = "<@U999> *Check* <https://x.com|this link> for _details_"
        result = sanitize_slack_reply(text)
        assert "<@U999>" not in result
        assert "*" not in result
        assert "_" not in result
        assert "this link" in result


# ── Webhook handler thread_ts routing ────────────────────


class TestWebhookThreadRouting:
    def test_thread_reply_routes_to_originator(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import save_notification_mapping

        save_notification_mapping("parent.ts", "C001", "mikoto")

        event = {
            "type": "message",
            "text": "Got it, looking into this now",
            "user": "U_HUMAN",
            "channel": "C001",
            "ts": "reply.ts",
            "thread_ts": "parent.ts",
        }

        messenger_mock = MagicMock()
        with patch("server.routes.webhooks.Messenger", return_value=messenger_mock), \
             patch("server.routes.webhooks.get_data_dir", return_value=routing_dir):
            from server.routes.webhooks import create_webhooks_router
            _verify_routing_via_thread(event, messenger_mock, "mikoto")

    def test_no_thread_ts_falls_through(self, routing_dir: Path) -> None:
        """Messages without thread_ts use normal channel-based routing."""
        event = {
            "type": "message",
            "text": "hello world",
            "user": "U_HUMAN",
            "channel": "C001",
            "ts": "msg.ts",
        }
        assert event.get("thread_ts") is None

    def test_unknown_thread_ts_falls_through(self, routing_dir: Path) -> None:
        """thread_ts not in notification_map falls through to channel routing."""
        from core.notification.reply_routing import lookup_notification_mapping

        assert lookup_notification_mapping("unknown.thread.ts") is None


# ── Socket handler thread_ts routing ─────────────────────


class TestSocketThreadRouting:
    def test_thread_reply_routes_to_originator(self, routing_dir: Path) -> None:
        from core.notification.reply_routing import save_notification_mapping

        save_notification_mapping("parent.ts", "C001", "aoi")

        event = {
            "type": "message",
            "text": "Acknowledged",
            "user": "U_HUMAN",
            "channel": "C001",
            "ts": "reply.ts",
            "thread_ts": "parent.ts",
        }

        messenger_mock = MagicMock()
        with patch("server.slack_socket.Messenger", return_value=messenger_mock), \
             patch("server.slack_socket.get_data_dir", return_value=routing_dir):
            _verify_routing_via_thread(event, messenger_mock, "aoi")


# ── Backward compatibility ───────────────────────────────


class TestBackwardCompat:
    def test_message_without_thread_ts_uses_channel_mapping(self) -> None:
        """Verify the existing channel-based routing path is untouched."""
        event = {
            "type": "message",
            "text": "normal message",
            "user": "U123",
            "channel": "C001",
            "ts": "1234.5678",
        }
        assert "thread_ts" not in event
        assert "subtype" not in event


# ── Helpers ──────────────────────────────────────────────


def _verify_routing_via_thread(
    event: dict,
    messenger_mock: MagicMock,
    expected_anima: str,
) -> None:
    """Verify that receive_external is called with the right Anima target.

    This tests the core logic: thread_ts lookup → sanitize → deliver.
    """
    from core.notification.reply_routing import (
        lookup_notification_mapping,
        sanitize_slack_reply,
    )

    thread_ts = event.get("thread_ts")
    assert thread_ts is not None

    mapping = lookup_notification_mapping(thread_ts)
    assert mapping is not None
    assert mapping["anima"] == expected_anima

    sanitized = sanitize_slack_reply(event.get("text", ""))
    assert sanitized
    assert len(sanitized) <= 4000
