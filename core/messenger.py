from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from core.schemas import Message

if TYPE_CHECKING:
    from broker.base import BrokerBackend

logger = logging.getLogger("animaworks.messenger")


class Messenger:
    """File-system based messaging with optional broker backend.

    Messages are JSON files in shared/inbox/{name}/.
    When a broker is provided, send_async() can publish via broker instead.
    """

    def __init__(
        self,
        shared_dir: Path,
        person_name: str,
        broker: BrokerBackend | None = None,
    ) -> None:
        self.shared_dir = shared_dir
        self.person_name = person_name
        self.inbox_dir = shared_dir / "inbox" / person_name
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._broker = broker

    def send(
        self,
        to: str,
        content: str,
        msg_type: str = "message",
        thread_id: str = "",
        reply_to: str = "",
    ) -> Message:
        msg = Message(
            from_person=self.person_name,
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
        logger.info("Message sent: %s -> %s (%s)", self.person_name, to, msg.id)
        return msg

    def reply(self, original: Message, content: str) -> Message:
        """Reply to a message, inheriting thread_id."""
        return self.send(
            to=original.from_person,
            content=content,
            thread_id=original.thread_id or original.id,
            reply_to=original.id,
        )

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
            processed_dir = self.inbox_dir / "processed"
            processed_dir.mkdir(exist_ok=True)
            for f in self.inbox_dir.glob("*.json"):
                f.rename(processed_dir / f.name)
        return messages

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
        """Send via broker if available, fall back to filesystem."""
        msg = Message(
            from_person=self.person_name,
            to_person=to,
            type=msg_type,
            content=content,
            thread_id=thread_id,
            reply_to=reply_to,
        )
        if not msg.thread_id:
            msg.thread_id = msg.id

        if self._broker and self._broker.is_connected():
            from broker.messages import BrokerMessage, MessageType

            broker_msg = BrokerMessage(
                type=MessageType.PERSON_MESSAGE,
                request_id=msg.id,
                person_name=to,
                payload=msg.model_dump(mode="json"),
            )
            await self._broker.publish(
                f"animaworks:person:{to}:inbox", broker_msg
            )
            logger.info(
                "Message sent via broker: %s -> %s (%s)",
                self.person_name, to, msg.id,
            )
        else:
            # Fall back to filesystem
            self.send(
                to=to,
                content=content,
                msg_type=msg_type,
                thread_id=thread_id,
                reply_to=reply_to,
            )
        return msg
