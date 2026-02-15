from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Human notification subsystem.

Provides ``HumanNotifier`` and channel implementations for sending
notifications from top-level Persons to human administrators via
external messaging services (Slack, LINE, Telegram, Chatwork, ntfy).
"""

from core.notification.notifier import HumanNotifier, NotificationChannel

__all__ = ["HumanNotifier", "NotificationChannel"]
