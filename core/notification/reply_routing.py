from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Reply routing for call_human notifications.

Maps Slack message timestamps (ts) to originating Anima names so that
threaded replies to call_human notifications can be routed back to the
Anima that sent the original notification.

Storage: ``{data_dir}/run/notification_map.json``
"""

import fcntl
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import get_data_dir

logger = logging.getLogger("animaworks.notification.reply_routing")

_MAX_AGE_DAYS = 7
_MAX_REPLY_LENGTH = 4000

# Slack mrkdwn patterns
_RE_USER_MENTION = re.compile(r"<@[A-Z0-9]+>")
_RE_LINK = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
_RE_LINK_BARE = re.compile(r"<(https?://[^>]+)>")
_RE_CHANNEL = re.compile(r"<#[A-Z0-9]+\|([^>]+)>")


def _map_path() -> Path:
    return get_data_dir() / "run" / "notification_map.json"


def _read_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupted notification_map.json; resetting")
        return {}


def _write_map(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Public API ──────────────────────────────────────────


def save_notification_mapping(
    ts: str,
    channel: str,
    anima_name: str,
) -> None:
    """Persist a Slack message ts → Anima mapping for reply routing."""
    path = _map_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = path.open("a+")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            fd.seek(0)
            raw = fd.read()
            data: dict[str, Any] = json.loads(raw) if raw.strip() else {}

            data[ts] = {
                "anima": anima_name,
                "channel": channel,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            _prune_old_entries_inplace(data)

            fd.seek(0)
            fd.truncate()
            fd.write(json.dumps(data, ensure_ascii=False, indent=2))
            fd.flush()
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
    except OSError:
        logger.exception("Failed to save notification mapping for ts=%s", ts)


def lookup_notification_mapping(thread_ts: str) -> dict[str, str] | None:
    """Look up which Anima sent the notification with the given ts.

    Returns ``{"anima": "...", "channel": "..."}`` or ``None``.
    """
    path = _map_path()
    data = _read_map(path)
    entry = data.get(thread_ts)
    if entry is None:
        return None
    return {"anima": entry["anima"], "channel": entry["channel"]}


def prune_old_entries(max_age_days: int = _MAX_AGE_DAYS) -> None:
    """Remove entries older than *max_age_days* from the mapping file."""
    path = _map_path()
    if not path.exists():
        return
    data = _read_map(path)
    before = len(data)
    _prune_old_entries_inplace(data, max_age_days)
    if len(data) < before:
        _write_map(path, data)


def _prune_old_entries_inplace(
    data: dict[str, Any],
    max_age_days: int = _MAX_AGE_DAYS,
) -> None:
    """Remove stale entries from *data* dict in-place."""
    now = datetime.now(timezone.utc)
    stale = [
        ts
        for ts, entry in data.items()
        if _age_days(entry.get("created_at", ""), now) > max_age_days
    ]
    for ts in stale:
        del data[ts]


def _age_days(iso_str: str, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(iso_str)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created).total_seconds() / 86400
    except (ValueError, TypeError):
        return float("inf")


def sanitize_slack_reply(text: str, max_length: int = _MAX_REPLY_LENGTH) -> str:
    """Strip Slack mrkdwn formatting and truncate for safe inbox delivery."""
    # Remove bot @mentions  <@U0123BOT>
    text = _RE_USER_MENTION.sub("", text)
    # <url|label> → label
    text = _RE_LINK.sub(r"\2", text)
    # <url> → url
    text = _RE_LINK_BARE.sub(r"\1", text)
    # <#C123|channel-name> → #channel-name
    text = _RE_CHANNEL.sub(r"#\1", text)
    # Bold *text* → text, italic _text_ → text, strike ~text~ → text
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)~([^~]+)~(?!\w)", r"\1", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text
