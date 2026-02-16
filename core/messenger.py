from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


import json
import logging
from datetime import date
from pathlib import Path

from core.schemas import Message

logger = logging.getLogger("animaworks.messenger")


class Messenger:
    """File-system based messaging.

    Messages are JSON files in shared/inbox/{name}/.
    """

    def __init__(
        self,
        shared_dir: Path,
        anima_name: str,
    ) -> None:
        self.shared_dir = shared_dir
        self.anima_name = anima_name
        self.inbox_dir = shared_dir / "inbox" / anima_name
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(
        self,
        to: str,
        content: str,
        msg_type: str = "message",
        thread_id: str = "",
        reply_to: str = "",
    ) -> Message:
        msg = Message(
            from_person=self.anima_name,
            to_person=to,
            type=msg_type,
            content=content,
            thread_id=thread_id,
            reply_to=reply_to,
        )
        # New thread: use message id as thread_id
        if not msg.thread_id:
            msg.thread_id = msg.id
        target_dir = self.shared_dir / "inbox" / to
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / f"{msg.id}.json"
        filepath.write_text(msg.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Message sent: %s -> %s (%s)", self.anima_name, to, msg.id)
        # Append to shared message log for activity timeline
        self._append_message_log(msg)
        return msg

    def reply(self, original: Message, content: str) -> Message:
        """Reply to a message, inheriting thread_id."""
        return self.send(
            to=original.from_person,
            content=content,
            thread_id=original.thread_id or original.id,
            reply_to=original.id,
        )

    def _append_message_log(self, msg: Message) -> None:
        """Append message event to shared activity log."""
        log_dir = self.shared_dir / "message_log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{date.today().isoformat()}.jsonl"
        entry = json.dumps({
            "timestamp": msg.timestamp.isoformat(),
            "from_person": msg.from_person,
            "to_person": msg.to_person,
            "type": msg.type,
            "summary": msg.content[:200],
            "message_id": msg.id,
            "thread_id": msg.thread_id,
        }, ensure_ascii=False)
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except OSError:
            logger.warning("Failed to append message log: %s", log_file)

    def receive(self) -> list[Message]:
        messages: list[Message] = []
        for f in sorted(self.inbox_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                messages.append(Message(**data))
            except Exception as e:
                logger.error("Failed to parse message %s: %s", f, e)
        return messages

    def receive_and_archive(self) -> list[Message]:
        messages = self.receive()
        if messages:
            self.archive_all()
        return messages

    def archive_all(self) -> int:
        """Move all unread messages in inbox to processed/."""
        processed_dir = self.inbox_dir / "processed"
        processed_dir.mkdir(exist_ok=True)
        count = 0
        for f in self.inbox_dir.glob("*.json"):
            f.rename(processed_dir / f.name)
            count += 1
        # Clean up non-JSON files that may have been left by Agent SDK
        for f in self.inbox_dir.iterdir():
            if f.is_file() and f.suffix != ".json" and not f.name.startswith("."):
                logger.warning("Cleaning up non-JSON file in inbox: %s", f.name)
                f.rename(processed_dir / f.name)
        return count

    def archive_from(self, sender: str) -> int:
        """Move messages from a specific sender to processed/.

        Only archives messages where ``from_person`` matches *sender*.
        Returns the number of archived messages.
        """
        processed_dir = self.inbox_dir / "processed"
        processed_dir.mkdir(exist_ok=True)
        count = 0
        for f in self.inbox_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("from_person") == sender:
                    f.rename(processed_dir / f.name)
                    count += 1
            except Exception as e:
                logger.error("Failed to check message %s: %s", f, e)
        return count

    def has_unread(self) -> bool:
        return any(self.inbox_dir.glob("*.json"))

    def unread_count(self) -> int:
        return len(list(self.inbox_dir.glob("*.json")))

    async def send_async(
        self,
        to: str,
        content: str,
        msg_type: str = "message",
        thread_id: str = "",
        reply_to: str = "",
    ) -> Message:
        """Async wrapper for filesystem-based send."""
        return self.send(
            to=to,
            content=content,
            msg_type=msg_type,
            thread_id=thread_id,
            reply_to=reply_to,
        )


# ── Message Log Reconciliation ──────────────────────────


def reconcile_message_log(shared_dir: Path) -> int:
    """Reconcile processed inbox messages into the shared message log.

    Scans ``shared/inbox/*/processed/*.json`` for all processed messages
    and appends any missing entries to ``shared/message_log/{date}.jsonl``.

    Args:
        shared_dir: Path to the shared runtime directory.

    Returns:
        Number of newly added log entries.
    """
    inbox_dir = shared_dir / "inbox"
    if not inbox_dir.exists():
        logger.info("reconcile_message_log: inbox dir does not exist, skipping")
        return 0

    log_dir = shared_dir / "message_log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Collect all known message IDs from existing log files
    known_ids: set[str] = set()
    for log_file in log_dir.glob("*.jsonl"):
        try:
            for line in log_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    mid = entry.get("message_id", "")
                    if mid:
                        known_ids.add(mid)
                except json.JSONDecodeError:
                    continue
        except OSError:
            logger.warning("Failed to read log file: %s", log_file)

    # Scan all processed messages across all anima inboxes
    added = 0
    for processed_dir in sorted(inbox_dir.glob("*/processed")):
        for msg_file in sorted(processed_dir.glob("*.json")):
            try:
                data = json.loads(msg_file.read_text(encoding="utf-8"))
                msg = Message(**data)
            except Exception:
                logger.warning("Skipping unparseable message: %s", msg_file)
                continue

            if msg.id in known_ids:
                continue

            # Build log entry in the same format as _append_message_log
            log_date = msg.timestamp.date().isoformat()
            log_file = log_dir / f"{log_date}.jsonl"
            entry = json.dumps({
                "timestamp": msg.timestamp.isoformat(),
                "from_person": msg.from_person,
                "to_person": msg.to_person,
                "type": msg.type,
                "summary": msg.content[:200],
                "message_id": msg.id,
                "thread_id": msg.thread_id,
            }, ensure_ascii=False)
            try:
                with log_file.open("a", encoding="utf-8") as f:
                    f.write(entry + "\n")
                known_ids.add(msg.id)
                added += 1
            except OSError:
                logger.warning("Failed to append reconciled entry: %s", log_file)

    logger.info("reconcile_message_log: added %d entries", added)
    return added
