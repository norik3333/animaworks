from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Organisation-wide audit data collection utility.

Collects structured audit data across all enabled Animas by reading
activity logs, status files, and task queues.  Used by the Activity
Report API and the CLI audit commands.
"""

import asyncio
import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from core.paths import get_animas_dir

logger = logging.getLogger(__name__)

_AUDIT_ENTRY_LIMIT = 10_000


# ── Data models ──────────────────────────────────────────────


@dataclass
class AnimaAuditEntry:
    """Audit metrics for a single Anima."""

    name: str
    enabled: bool
    model: str
    supervisor: str | None
    role: str | None
    total_entries: int
    type_counts: dict[str, int]
    messages_sent: int
    messages_received: int
    errors: int
    tasks_total: int
    tasks_pending: int
    tasks_done: int
    peers_sent: dict[str, int]
    peers_received: dict[str, int]
    first_activity: str | None
    last_activity: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrgAuditReport:
    """Organisation-wide audit report aggregating all Anima metrics."""

    date: str
    animas: list[AnimaAuditEntry]
    total_entries: int = 0
    total_messages: int = 0
    total_errors: int = 0
    total_tasks_done: int = 0
    active_anima_count: int = 0
    disabled_anima_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["animas"] = [a.to_dict() for a in self.animas]
        return d


# ── Collection logic ─────────────────────────────────────────


def _collect_single_anima(anima_dir: Path, days: int) -> AnimaAuditEntry | None:
    """Collect audit data for one Anima (synchronous, I/O-bound)."""
    name = anima_dir.name
    status_file = anima_dir / "status.json"

    enabled = True
    model = "unknown"
    supervisor: str | None = None
    role: str | None = None

    if status_file.exists():
        try:
            sdata = json.loads(status_file.read_text(encoding="utf-8"))
            enabled = sdata.get("enabled", True)
            model = sdata.get("model", "unknown")
            supervisor = sdata.get("supervisor") or None
            role = sdata.get("role") or None
        except (json.JSONDecodeError, OSError):
            logger.debug("Failed to read status.json for %s", name)

    from core.memory.activity import ActivityLogger

    al = ActivityLogger(anima_dir)
    entries = al.recent(days=days, limit=_AUDIT_ENTRY_LIMIT)

    type_counts: Counter[str] = Counter()
    for e in entries:
        type_counts[e.type] += 1

    sent = [e for e in entries if e.type in ("message_sent", "dm_sent")]
    received = [e for e in entries if e.type in ("message_received", "dm_received")]
    error_entries = [e for e in entries if e.type == "error"]

    peer_sent: dict[str, int] = {}
    peer_recv: dict[str, int] = {}
    for e in sent:
        peer = e.to_person or "unknown"
        peer_sent[peer] = peer_sent.get(peer, 0) + 1
    for e in received:
        peer = e.from_person or "unknown"
        peer_recv[peer] = peer_recv.get(peer, 0) + 1

    tasks_total = 0
    tasks_pending = 0
    tasks_done = 0
    try:
        from core.memory.task_queue import TaskQueueManager

        tqm = TaskQueueManager(anima_dir)
        all_tasks = tqm.list_tasks()
        tasks_total = len(all_tasks)
        tasks_pending = len([t for t in all_tasks if t.status in ("pending", "in_progress", "blocked")])
        tasks_done = len([t for t in all_tasks if t.status == "done"])
    except Exception:
        logger.debug("Failed to read task queue for %s", name, exc_info=True)

    first_activity = entries[0].ts if entries else None
    last_activity = entries[-1].ts if entries else None

    return AnimaAuditEntry(
        name=name,
        enabled=enabled,
        model=model,
        supervisor=supervisor,
        role=role,
        total_entries=len(entries),
        type_counts=dict(type_counts),
        messages_sent=len(sent),
        messages_received=len(received),
        errors=len(error_entries),
        tasks_total=tasks_total,
        tasks_pending=tasks_pending,
        tasks_done=tasks_done,
        peers_sent=peer_sent,
        peers_received=peer_recv,
        first_activity=first_activity,
        last_activity=last_activity,
    )


async def collect_org_audit(
    date: str,
    *,
    days: int = 1,
) -> OrgAuditReport:
    """Collect audit data for all Animas.

    Runs I/O-bound collection in a thread pool via asyncio for parallelism.

    Args:
        date: Report date string (YYYY-MM-DD).
        days: Number of days to scan (default 1).

    Returns:
        OrgAuditReport with per-anima metrics and org-level aggregates.
    """
    animas_dir = get_animas_dir()
    if not animas_dir.exists():
        return OrgAuditReport(date=date, animas=[])

    anima_dirs = sorted([d for d in animas_dir.iterdir() if d.is_dir() and (d / "status.json").exists()])

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _collect_single_anima, d, days) for d in anima_dirs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    animas: list[AnimaAuditEntry] = []
    for r in results:
        if isinstance(r, AnimaAuditEntry):
            animas.append(r)
        elif isinstance(r, Exception):
            logger.warning("Audit collection failed for an anima: %s", r)

    total_entries = sum(a.total_entries for a in animas)
    total_messages = sum(a.messages_sent + a.messages_received for a in animas)
    total_errors = sum(a.errors for a in animas)
    total_tasks_done = sum(a.tasks_done for a in animas)
    active_count = sum(1 for a in animas if a.enabled)
    disabled_count = sum(1 for a in animas if not a.enabled)

    return OrgAuditReport(
        date=date,
        animas=animas,
        total_entries=total_entries,
        total_messages=total_messages,
        total_errors=total_errors,
        total_tasks_done=total_tasks_done,
        active_anima_count=active_count,
        disabled_anima_count=disabled_count,
    )
