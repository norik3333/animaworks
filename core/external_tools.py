from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""External tool dispatcher.

Maps tool schema names to the appropriate module function/class method call.
Each external tool module (web_search, slack, chatwork, …) is loaded
dynamically and executed here.
"""

import json
import logging
from typing import Any

logger = logging.getLogger("animaworks.external_tools")


class ExternalToolDispatcher:
    """Dispatch tool calls to external tool modules.

    External tools are loaded dynamically from ``core.tools`` based on the
    ``tool_registry`` (allowed tools from permissions.md).
    """

    def __init__(self, tool_registry: list[str]) -> None:
        self._registry = tool_registry

    def dispatch(self, name: str, args: dict[str, Any]) -> str | None:
        """Execute an external tool by schema name.

        Returns:
            Result string on success, or ``None`` if no matching tool found.
        """
        if not self._registry:
            return None

        import importlib

        from core.tools import TOOL_MODULES

        for tool_name, module_path in TOOL_MODULES.items():
            if tool_name not in self._registry:
                continue
            try:
                mod = importlib.import_module(module_path)
                schemas = mod.get_tool_schemas() if hasattr(mod, "get_tool_schemas") else []
                schema_names = [s["name"] for s in schemas]
                if name not in schema_names:
                    continue

                result = _execute(mod, schema_name=name, args=args)
                if isinstance(result, (dict, list)):
                    return json.dumps(result, ensure_ascii=False, indent=2, default=str)
                return str(result) if result is not None else "(no output)"
            except Exception as e:
                logger.warning("External tool %s failed: %s", name, e)
                return f"Error executing {name}: {e}"

        return None


# ── Execution dispatch table ─────────────────────────────────
#
# Each schema_name is mapped to the correct function/method call on its module.
# This is deliberately explicit rather than reflection-based so that call
# signatures, default arguments, and post-processing remain visible and
# auditable in one place.


def _execute(mod: Any, *, schema_name: str, args: dict[str, Any]) -> Any:
    """Execute the appropriate function for *schema_name*."""

    # ── web_search ────────────────────────────────────────
    if schema_name == "web_search":
        return mod.search(**args)

    # ── x_search ──────────────────────────────────────────
    if schema_name == "x_search":
        client = mod.XSearchClient()
        return client.search_recent(
            query=args["query"],
            max_results=args.get("max_results", 10),
            days=args.get("days", 7),
        )
    if schema_name == "x_user_tweets":
        client = mod.XSearchClient()
        return client.get_user_tweets(
            username=args["username"],
            max_results=args.get("max_results", 10),
            days=args.get("days"),
        )

    # ── chatwork ──────────────────────────────────────────
    if schema_name == "chatwork_send":
        client = mod.ChatworkClient()
        room_id = client.resolve_room_id(args["room"])
        return client.post_message(room_id, args["message"])
    if schema_name == "chatwork_messages":
        client = mod.ChatworkClient()
        room_id = client.resolve_room_id(args["room"])
        cache = mod.MessageCache()
        try:
            msgs = client.get_messages(room_id, force=True)
            if msgs:
                cache.upsert_messages(room_id, msgs)
                cache.update_sync_state(room_id)
            return cache.get_recent(room_id, limit=args.get("limit", 20))
        finally:
            cache.close()
    if schema_name == "chatwork_search":
        client = mod.ChatworkClient()
        cache = mod.MessageCache()
        try:
            room_id = None
            if args.get("room"):
                room_id = client.resolve_room_id(args["room"])
            return cache.search(
                args["keyword"], room_id=room_id, limit=args.get("limit", 50),
            )
        finally:
            cache.close()
    if schema_name == "chatwork_unreplied":
        client = mod.ChatworkClient()
        cache = mod.MessageCache()
        try:
            my_info = client.me()
            my_id = str(my_info["account_id"])
            return cache.find_unreplied(
                my_id, exclude_toall=not args.get("include_toall", False),
            )
        finally:
            cache.close()
    if schema_name == "chatwork_rooms":
        client = mod.ChatworkClient()
        return client.rooms()

    # ── slack ─────────────────────────────────────────────
    if schema_name == "slack_send":
        client = mod.SlackClient()
        channel_id = client.resolve_channel(args["channel"])
        return client.post_message(
            channel_id,
            args["message"],
            thread_ts=args.get("thread_ts"),
        )
    if schema_name == "slack_messages":
        client = mod.SlackClient()
        channel_id = client.resolve_channel(args["channel"])
        cache = mod.MessageCache()
        try:
            limit = args.get("limit", 20)
            msgs = client.channel_history(channel_id, limit=limit)
            if msgs:
                for m in msgs:
                    uid = m.get("user", m.get("bot_id", ""))
                    if uid:
                        m["user_name"] = client.resolve_user_name(uid)
                cache.upsert_messages(channel_id, msgs)
                cache.update_sync_state(channel_id)
            return cache.get_recent(channel_id, limit=limit)
        finally:
            cache.close()
    if schema_name == "slack_search":
        client = mod.SlackClient()
        cache = mod.MessageCache()
        try:
            channel_id = None
            if args.get("channel"):
                channel_id = client.resolve_channel(args["channel"])
            return cache.search(
                args["keyword"], channel_id=channel_id, limit=args.get("limit", 50),
            )
        finally:
            cache.close()
    if schema_name == "slack_unreplied":
        client = mod.SlackClient()
        cache = mod.MessageCache()
        try:
            client.auth_test()
            return cache.find_unreplied(client.my_user_id)
        finally:
            cache.close()
    if schema_name == "slack_channels":
        client = mod.SlackClient()
        return client.channels()

    # ── gmail ─────────────────────────────────────────────
    if schema_name == "gmail_unread":
        client = mod.GmailClient()
        emails = client.get_unread_emails(max_results=args.get("max_results", 20))
        return [
            {"id": e.id, "from": e.from_addr, "subject": e.subject, "snippet": e.snippet}
            for e in emails
        ]
    if schema_name == "gmail_read_body":
        client = mod.GmailClient()
        return client.get_email_body(args["message_id"])
    if schema_name == "gmail_draft":
        client = mod.GmailClient()
        result = client.create_draft(
            to=args["to"],
            subject=args["subject"],
            body=args["body"],
            thread_id=args.get("thread_id"),
            in_reply_to=args.get("in_reply_to"),
        )
        return {"success": result.success, "draft_id": result.draft_id, "error": result.error}

    # ── local_llm ─────────────────────────────────────────
    if schema_name == "local_llm_generate":
        client = mod.OllamaClient(
            server=args.get("server", "auto"),
            model=args.get("model"),
            hint=args.get("hint"),
        )
        return client.generate(
            prompt=args["prompt"],
            system=args.get("system", ""),
            temperature=args.get("temperature", 0.7),
            max_tokens=args.get("max_tokens", 4096),
            think=args.get("think", "off"),
        )
    if schema_name == "local_llm_chat":
        client = mod.OllamaClient(
            server=args.get("server", "auto"),
            model=args.get("model"),
            hint=args.get("hint"),
        )
        return client.chat(
            messages=args["messages"],
            system=args.get("system", ""),
            temperature=args.get("temperature", 0.7),
            max_tokens=args.get("max_tokens", 4096),
            think=args.get("think", "off"),
        )
    if schema_name == "local_llm_models":
        client = mod.OllamaClient(server=args.get("server", "auto"))
        return client.list_models()
    if schema_name == "local_llm_status":
        client = mod.OllamaClient()
        return client.server_status()

    # ── transcribe ────────────────────────────────────────
    if schema_name == "transcribe_audio":
        return mod.process_audio(
            audio_path=args["audio_path"],
            language=args.get("language"),
            model=args.get("model"),
            raw_only=args.get("raw_only", False),
            custom_prompt=args.get("custom_prompt"),
        )

    # ── aws_collector ─────────────────────────────────────
    if schema_name == "aws_ecs_status":
        collector = mod.AWSCollector(region=args.get("region"))
        return collector.get_ecs_status(args["cluster"], args["service"])
    if schema_name == "aws_error_logs":
        collector = mod.AWSCollector(region=args.get("region"))
        return collector.get_error_logs(
            log_group=args["log_group"],
            hours=args.get("hours", 1),
            patterns=args.get("patterns"),
        )
    if schema_name == "aws_metrics":
        collector = mod.AWSCollector(region=args.get("region"))
        return collector.get_metrics(
            cluster=args["cluster"],
            service=args["service"],
            metric=args.get("metric", "CPUUtilization"),
            hours=args.get("hours", 1),
        )

    # ── github ────────────────────────────────────────────
    if schema_name == "github_list_issues":
        client = mod.GitHubClient(repo=args.get("repo"))
        return client.list_issues(
            state=args.get("state", "open"),
            labels=args.get("labels"),
            limit=args.get("limit", 20),
        )
    if schema_name == "github_create_issue":
        client = mod.GitHubClient(repo=args.get("repo"))
        return client.create_issue(
            title=args["title"],
            body=args.get("body", ""),
            labels=args.get("labels"),
        )
    if schema_name == "github_list_prs":
        client = mod.GitHubClient(repo=args.get("repo"))
        return client.list_prs(
            state=args.get("state", "open"),
            limit=args.get("limit", 20),
        )
    if schema_name == "github_create_pr":
        client = mod.GitHubClient(repo=args.get("repo"))
        return client.create_pr(
            title=args["title"],
            body=args.get("body", ""),
            head=args["head"],
            base=args.get("base", "main"),
            draft=args.get("draft", False),
        )

    raise ValueError(f"No handler for tool schema: {schema_name}")