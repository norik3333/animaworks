from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Slack notification channel via Incoming Webhook."""

import logging
from typing import Any

import httpx

from core.notification.notifier import NotificationChannel, register_channel

logger = logging.getLogger("animaworks.notification.slack")


@register_channel("slack")
class SlackChannel(NotificationChannel):
    """Send notifications to Slack via Incoming Webhook URL."""

    @property
    def channel_type(self) -> str:
        return "slack"

    async def send(
        self,
        subject: str,
        body: str,
        priority: str = "normal",
        *,
        person_name: str = "",
    ) -> str:
        webhook_url = self._config.get("webhook_url", "")
        if not webhook_url:
            # Try env var reference
            webhook_url = self._resolve_env("webhook_url_env")
        if not webhook_url:
            return "slack: ERROR - webhook_url not configured"

        prefix = f"[{priority.upper()}] " if priority in ("high", "urgent") else ""
        sender = f" (from {person_name})" if person_name else ""
        text = f"{prefix}*{subject}*{sender}\n{body}"[:40000]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(webhook_url, json={"text": text})
                resp.raise_for_status()
            logger.info("Slack notification sent: %s", subject[:50])
            return "slack: OK"
        except httpx.HTTPStatusError as e:
            msg = f"slack: ERROR - HTTP {e.response.status_code}"
            logger.error(msg)
            return msg
        except Exception as e:
            msg = f"slack: ERROR - {e}"
            logger.error(msg)
            return msg
