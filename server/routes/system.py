from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Request

logger = logging.getLogger("animaworks.routes.system")


def _parse_cron_jobs(animas_dir: Path, anima_names: list[str]) -> list[dict]:
    """Parse cron.md files from all animas and return job definitions."""
    jobs: list[dict] = []
    for name in anima_names:
        cron_path = animas_dir / name / "cron.md"
        if not cron_path.exists():
            continue
        try:
            content = cron_path.read_text(encoding="utf-8")
        except OSError:
            continue
        # Parse markdown sections: ## Title (schedule info)
        # Skip commented-out sections (inside <!-- --> blocks)
        in_comment = False
        current_title = ""
        current_type = ""
        for line in content.splitlines():
            stripped = line.strip()
            if "<!--" in stripped:
                in_comment = True
            if "-->" in stripped:
                in_comment = False
                continue
            if in_comment:
                continue
            if stripped.startswith("## "):
                current_title = stripped[3:].strip()
                current_type = ""
            elif stripped.startswith("type:"):
                current_type = stripped[5:].strip()
            elif current_title and current_type:
                # Extract schedule from title parentheses
                schedule = ""
                m = re.search(r"[（(](.+?)[）)]", current_title)
                if m:
                    schedule = m.group(1)
                jobs.append({
                    "id": f"cron-{name}-{len(jobs)}",
                    "name": current_title,
                    "anima": name,
                    "type": current_type,
                    "schedule": schedule,
                    "next_run": None,
                })
                current_title = ""
                current_type = ""
    return jobs


def create_system_router() -> APIRouter:
    router = APIRouter()

    @router.get("/shared/users")
    async def list_shared_users(request: Request):
        """List registered user names from shared/users/."""
        users_dir = request.app.state.shared_dir / "users"
        if not users_dir.is_dir():
            return []
        return [d.name for d in sorted(users_dir.iterdir()) if d.is_dir()]

    @router.get("/system/status")
    async def system_status(request: Request):
        supervisor = request.app.state.supervisor
        anima_names = request.app.state.anima_names

        # Get all process statuses
        process_statuses = supervisor.get_all_status()

        return {
            "animas": len(anima_names),
            "processes": process_statuses,
            "scheduler_running": supervisor.is_scheduler_running(),
        }

    @router.post("/system/reload")
    async def reload_animas(request: Request):
        """Full sync: add new animas, refresh existing, remove deleted."""
        supervisor = request.app.state.supervisor
        animas_dir = request.app.state.animas_dir
        current_names = set(request.app.state.anima_names)

        added: list[str] = []
        refreshed: list[str] = []
        removed: list[str] = []

        # Discover current animas on disk
        from core.supervisor.manager import ProcessSupervisor

        on_disk: set[str] = set()
        if animas_dir.exists():
            for anima_dir in sorted(animas_dir.iterdir()):
                if not anima_dir.is_dir():
                    continue
                if not (anima_dir / "identity.md").exists():
                    continue
                name = anima_dir.name

                # Respect status.json: skip disabled animas
                if not ProcessSupervisor.read_anima_enabled(anima_dir):
                    on_disk.add(name)
                    continue

                on_disk.add(name)

                if name not in current_names:
                    # New anima - start process
                    await supervisor.start_anima(name)
                    request.app.state.anima_names.append(name)
                    added.append(name)
                    logger.info("Hot-loaded anima: %s", name)
                else:
                    # Existing anima — restart to pick up file changes
                    await supervisor.restart_anima(name)
                    refreshed.append(name)
                    logger.info("Refreshed anima: %s", name)

        # Remove animas whose directories no longer exist
        for name in list(current_names):
            if name not in on_disk:
                await supervisor.stop_anima(name)
                request.app.state.anima_names.remove(name)
                removed.append(name)
                logger.info("Unloaded anima: %s", name)

        return {
            "added": added,
            "refreshed": refreshed,
            "removed": removed,
            "total": len(request.app.state.anima_names),
        }

    # ── Connections ─────────────────────────────────────────

    @router.get("/system/connections")
    async def system_connections(request: Request):
        """Return WebSocket and process connection info."""
        ws_manager = request.app.state.ws_manager
        supervisor = request.app.state.supervisor

        return {
            "websocket": {
                "connected_clients": (
                    len(ws_manager.active_connections)
                    if hasattr(ws_manager, "active_connections")
                    else 0
                ),
            },
            "processes": {
                name: supervisor.get_process_status(name)
                for name in request.app.state.anima_names
            },
        }

    # ── Scheduler ──────────────────────────────────────────

    @router.get("/system/scheduler")
    async def system_scheduler(request: Request):
        """Return scheduler status and job information."""
        supervisor = request.app.state.supervisor
        animas_dir = request.app.state.animas_dir
        anima_names = request.app.state.anima_names

        # Get configured jobs from cron.md files (for display)
        jobs = _parse_cron_jobs(animas_dir, anima_names)

        # Get system scheduler jobs
        system_jobs = []
        if supervisor.scheduler:
            for job in supervisor.scheduler.get_jobs():
                system_jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "anima": "system",
                    "type": "consolidation",
                    "schedule": str(job.trigger),
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                })

        return {
            "running": supervisor.is_scheduler_running(),
            "system_jobs": system_jobs,
            "anima_jobs": jobs,
        }

    # ── Activity ───────────────────────────────────────────

    @router.get("/activity/recent")
    async def get_recent_activity(
        request: Request,
        hours: int = 48,
        anima: str | None = None,
        offset: int = 0,
        limit: int = 100,
        event_type: str | None = None,
    ):
        """Return recent activity events aggregated across animas."""
        from datetime import date as date_type
        from datetime import datetime, timedelta, timezone

        from core.config.models import load_model_config
        from core.memory.conversation import ConversationMemory
        from core.memory.shortterm import ShortTermMemory

        animas_dir = request.app.state.animas_dir
        shared_dir = request.app.state.shared_dir
        anima_names = request.app.state.anima_names
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        events: list[dict] = []

        # Clamp limit
        limit = max(1, min(limit, 500))
        offset = max(0, offset)

        # Parse event_type filter (comma-separated)
        type_filter: set[str] | None = None
        if event_type:
            type_filter = {t.strip() for t in event_type.split(",") if t.strip()}

        target_names = (
            [anima] if anima and anima in anima_names else anima_names
        )

        for name in target_names:
            anima_dir = animas_dir / name
            if not anima_dir.exists():
                continue

            # Short-term memory archives (session history)
            stm = ShortTermMemory(anima_dir)
            archive_dir = stm._archive_dir
            if archive_dir.exists():
                for json_file in sorted(
                    archive_dir.glob("*.json"), reverse=True,
                ):
                    try:
                        data = json.loads(
                            json_file.read_text(encoding="utf-8"),
                        )
                        ts_str = data.get("timestamp", "")
                        ts = (
                            datetime.fromisoformat(ts_str) if ts_str else None
                        )
                        if ts and ts.replace(tzinfo=timezone.utc) < cutoff:
                            break
                        events.append({
                            "type": "session",
                            "animas": [name],
                            "timestamp": ts_str,
                            "summary": (
                                data.get("trigger", "")
                                + ": "
                                + data.get("original_prompt", "")[:80]
                            ),
                            "metadata": {
                                "trigger": data.get("trigger", ""),
                                "turn_count": data.get("turn_count", 0),
                                "context_usage_ratio": data.get(
                                    "context_usage_ratio", 0,
                                ),
                            },
                        })
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue

            # Conversation transcripts (today)
            try:
                model_config = load_model_config(anima_dir)
                conv = ConversationMemory(anima_dir, model_config)
                today = date_type.today().isoformat()
                messages = conv.load_transcript(today)
                for msg in messages:
                    ts_str = msg.get("timestamp", "")
                    events.append({
                        "type": "chat",
                        "animas": [name],
                        "timestamp": ts_str,
                        "summary": (msg.get("content", ""))[:80],
                        "metadata": {"role": msg.get("role", "")},
                    })
            except Exception:
                logger.warning("Failed to load transcripts for %s", name, exc_info=True)

            # Heartbeat history (date-split directory or legacy single file)
            hb_dir = anima_dir / "shortterm" / "heartbeat_history"
            hb_legacy = anima_dir / "shortterm" / "heartbeat_history.jsonl"
            hb_files: list[Path] = []
            if hb_dir.exists():
                hb_files = sorted(hb_dir.glob("*.jsonl"), reverse=True)
            elif hb_legacy.exists():
                hb_files = [hb_legacy]
            for hb_file in hb_files:
                try:
                    for line in hb_file.read_text(encoding="utf-8").strip().splitlines():
                        try:
                            entry = json.loads(line)
                            ts_str = entry.get("timestamp", "")
                            ts = datetime.fromisoformat(ts_str) if ts_str else None
                            if ts and ts.replace(tzinfo=timezone.utc) < cutoff:
                                continue
                            events.append({
                                "type": "heartbeat",
                                "animas": [name],
                                "timestamp": ts_str,
                                "summary": entry.get("summary", "")[:80],
                                "metadata": {
                                    "trigger": entry.get("trigger", ""),
                                    "action": entry.get("action", ""),
                                    "duration_ms": entry.get("duration_ms", 0),
                                },
                            })
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
                except Exception:
                    logger.warning("Failed to load heartbeat history for %s", name, exc_info=True)

            # Cron execution logs
            cron_log_dir = anima_dir / "state" / "cron_logs"
            if cron_log_dir.exists():
                try:
                    for log_file in sorted(cron_log_dir.glob("*.jsonl"), reverse=True):
                        for line in log_file.read_text(encoding="utf-8").strip().splitlines():
                            try:
                                entry = json.loads(line)
                                ts_str = entry.get("timestamp", "")
                                ts = datetime.fromisoformat(ts_str) if ts_str else None
                                if ts and ts.replace(tzinfo=timezone.utc) < cutoff:
                                    continue
                                summary = entry.get("summary") or entry.get("task", "")
                                if "exit_code" in entry:
                                    summary = f"{entry.get('task', '')}: exit_code={entry['exit_code']}"
                                events.append({
                                    "type": "cron",
                                    "animas": [name],
                                    "timestamp": ts_str,
                                    "summary": summary[:80],
                                    "metadata": {
                                        "task": entry.get("task", ""),
                                        "duration_ms": entry.get("duration_ms", 0),
                                        "exit_code": entry.get("exit_code"),
                                    },
                                })
                            except (json.JSONDecodeError, TypeError, ValueError):
                                continue
                except Exception:
                    logger.warning("Failed to load cron logs for %s", name, exc_info=True)

        # Inter-anima message logs (shared across all animas)
        msg_log_dir = shared_dir / "message_log"
        if msg_log_dir.exists():
            anima_filter = set(target_names)
            try:
                for log_file in sorted(msg_log_dir.glob("*.jsonl"), reverse=True):
                    for line in log_file.read_text(encoding="utf-8").strip().splitlines():
                        try:
                            entry = json.loads(line)
                            ts_str = entry.get("timestamp", "")
                            ts = datetime.fromisoformat(ts_str) if ts_str else None
                            if ts and ts.replace(tzinfo=timezone.utc) < cutoff:
                                continue
                            from_p = entry.get("from_person", "")
                            to_p = entry.get("to_person", "")
                            # Include if either sender or receiver matches anima filter
                            if anima and from_p not in anima_filter and to_p not in anima_filter:
                                continue
                            events.append({
                                "type": "message",
                                "animas": [from_p, to_p],
                                "timestamp": ts_str,
                                "summary": f"{from_p} → {to_p}: {entry.get('summary', '')[:60]}",
                                "metadata": {
                                    "from_person": from_p,
                                    "to_person": to_p,
                                    "message_id": entry.get("message_id", ""),
                                    "thread_id": entry.get("thread_id", ""),
                                    "text": entry.get("summary", ""),
                                },
                            })
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue
            except Exception:
                logger.warning("Failed to load message logs", exc_info=True)

        # Sort descending by timestamp
        events.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        # Apply type filter
        if type_filter:
            events = [e for e in events if e["type"] in type_filter]

        # Pagination
        total = len(events)
        paginated = events[offset:offset + limit]

        return {
            "events": paginated,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total,
        }

    return router
