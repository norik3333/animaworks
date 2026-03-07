# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Notion integration for AnimaWorks.

Provides:
- NotionClient: Notion API wrapper with rate-limit retry
- blocks_to_markdown: Convert Notion blocks to Markdown
- get_tool_schemas(): Anthropic tool_use schemas (returns [] for use_tool)
- cli_main(): standalone CLI entry point
- dispatch(): routes notion_* actions
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from core.i18n import t
from core.tools._base import ToolConfigError, get_credential, logger
from core.tools._retry import retry_on_rate_limit

# ── Execution Profile ─────────────────────────────────────

EXECUTION_PROFILE: dict[str, dict[str, object]] = {
    "search": {"expected_seconds": 15, "background_eligible": False},
    "get_page": {"expected_seconds": 5, "background_eligible": False},
    "get_page_content": {"expected_seconds": 10, "background_eligible": False},
    "get_database": {"expected_seconds": 5, "background_eligible": False},
    "query": {"expected_seconds": 15, "background_eligible": False},
    "create_page": {"expected_seconds": 10, "background_eligible": False},
    "update_page": {"expected_seconds": 10, "background_eligible": False},
    "create_database": {"expected_seconds": 10, "background_eligible": False},
}

MAX_PAYLOAD_BYTES = 500_000
RATE_LIMIT_RETRY_MAX = 5
RATE_LIMIT_WAIT_DEFAULT = 30


# ── Exception hierarchy ───────────────────────────────────


class NotionAPIError(Exception):
    """Base exception for Notion API errors."""

    pass


class RateLimitError(NotionAPIError):
    """Raised when Notion API returns HTTP 429."""

    def __init__(self, retry_after: float, response: Any) -> None:
        self.retry_after = retry_after
        self.response = response
        super().__init__(t("notion.rate_limited"))


class ServerError(NotionAPIError):
    """Raised when Notion API returns 5xx."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(t("notion.server_error", status=status_code, body=body))


# ── blocks_to_markdown ────────────────────────────────────


def _rich_text_to_markdown(rich_text: list[dict[str, Any]]) -> str:
    """Convert Notion rich_text array to Markdown with annotations."""
    parts: list[str] = []
    for rt in rich_text or []:
        if rt.get("type") == "mention":
            # Mention: user, page, database, date, etc.
            mention = rt.get("mention", {})
            if "page" in mention:
                parts.append(f"[page]({build_page_url(mention['page'].get('id', ''))})")
            elif "database" in mention:
                parts.append("[database]")
            elif "date" in mention:
                date_obj = mention["date"]
                if date_obj.get("end"):
                    parts.append(f"{date_obj.get('start', '')} - {date_obj.get('end', '')}")
                else:
                    parts.append(str(date_obj.get("start", "")))
            elif "user" in mention:
                parts.append("[user]")
            else:
                parts.append(rt.get("plain_text", ""))
            continue
        if rt.get("type") == "equation":
            expr = rt.get("equation", {}).get("expression", "")
            parts.append(f"${expr}$")
            continue
        content = rt.get("plain_text", rt.get("text", {}).get("content", ""))
        link = rt.get("href") or (
            rt.get("text", {}).get("link", {}).get("url") if isinstance(rt.get("text"), dict) else None
        )
        ann = rt.get("annotations", {}) or {}
        if ann.get("code"):
            content = f"`{content}`"
        else:
            if ann.get("bold"):
                content = f"**{content}**"
            if ann.get("italic"):
                content = f"*{content}*"
            if ann.get("strikethrough"):
                content = f"~~{content}~~"
            if link:
                content = f"[{content}]({link})"
        parts.append(content)
    return "".join(parts)


def blocks_to_markdown(blocks: list[dict[str, Any]]) -> str:
    """Convert Notion block objects to Markdown.

    Supports: paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item,
    to_do, toggle, code, quote, callout, divider, image, bookmark, link_preview,
    table (with table_row children), child_page, child_database.
    Unknown types become HTML comments.
    """
    lines: list[str] = []

    for block in blocks:
        btype = block.get("type", "unsupported")
        if block.get("in_trash", False):
            continue

        if btype == "paragraph":
            body = block.get("paragraph", {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            if text:
                lines.append(text)
            lines.append("")

        elif btype in ("heading_1", "heading_2", "heading_3"):
            level = int(btype.split("_")[1])
            body = block.get(btype, {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"{'#' * level} {text}")
            lines.append("")

        elif btype == "bulleted_list_item":
            body = block.get("bulleted_list_item", {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"- {text}")
            lines.append("")

        elif btype == "numbered_list_item":
            body = block.get("numbered_list_item", {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"1. {text}")
            lines.append("")

        elif btype == "to_do":
            body = block.get("to_do", {})
            checked = body.get("checked", False)
            text = _rich_text_to_markdown(body.get("rich_text", []))
            box = "[x]" if checked else "[ ]"
            lines.append(f"- {box} {text}")
            lines.append("")

        elif btype == "toggle":
            body = block.get("toggle", {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            children = block.get("_children", [])
            if children:
                child_md = blocks_to_markdown(children)
                lines.append("<details>")
                lines.append(f"<summary>▶ {text}</summary>")
                lines.append("")
                lines.append(child_md.strip())
                lines.append("</details>")
            else:
                lines.append(f"> ▶ {text}")
            lines.append("")

        elif btype == "code":
            body = block.get("code", {})
            lang = body.get("language", "plain text")
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"```{lang}")
            lines.append(text)
            lines.append("```")
            lines.append("")

        elif btype == "quote":
            body = block.get("quote", {})
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"> {text}")
            lines.append("")

        elif btype == "callout":
            body = block.get("callout", {})
            icon = body.get("icon", {})
            emoji = ""
            if isinstance(icon, dict) and "emoji" in icon:
                emoji = icon.get("emoji", "💡") + " "
            text = _rich_text_to_markdown(body.get("rich_text", []))
            lines.append(f"> {emoji}{text}")
            lines.append("")

        elif btype == "divider":
            lines.append("---")
            lines.append("")

        elif btype == "image":
            body = block.get("image", {})
            url = ""
            if body.get("type") == "external":
                url = body.get("external", {}).get("url", "")
            elif body.get("type") == "file":
                url = body.get("file", {}).get("url", "")
            caption = _rich_text_to_markdown(body.get("caption", []))
            cap = f" {caption}" if caption else ""
            lines.append(f"![image]({url}){cap}")
            lines.append("")

        elif btype == "bookmark":
            body = block.get("bookmark", {})
            url = body.get("url", "")
            caption = _rich_text_to_markdown(body.get("caption", []))
            text = caption or url
            lines.append(f"[{text}]({url})")
            lines.append("")

        elif btype == "link_preview":
            body = block.get("link_preview", {})
            url = body.get("url", "")
            lines.append(f"[{url}]({url})")
            lines.append("")

        elif btype == "table":
            children = block.get("_children", [])
            rows: list[list[str]] = []
            for row_block in children:
                if row_block.get("type") == "table_row":
                    cells = row_block.get("table_row", {}).get("cells", [])
                    row_texts = [_rich_text_to_markdown(c) for c in cells]
                    rows.append(row_texts)
            if rows:
                # First row as header
                lines.append("| " + " | ".join(rows[0]) + " |")
                lines.append("|" + "|".join(["---"] * len(rows[0])) + "|")
                for r in rows[1:]:
                    lines.append("| " + " | ".join(r) + " |")
            lines.append("")

        elif btype == "child_page":
            body = block.get("child_page", {})
            title = body.get("title", "Untitled")
            lines.append(f"📄 [{title}]")
            lines.append("")

        elif btype == "child_database":
            body = block.get("child_database", {})
            title = body.get("title", "Untitled")
            lines.append(f"📊 [{title}]")
            lines.append("")

        else:
            lines.append(f"<!-- unsupported: {btype} -->")
            lines.append("")

    return "\n".join(lines).rstrip()


# ── NotionClient ──────────────────────────────────────────


def build_page_url(page_id: str) -> str:
    """Build Notion page URL from page_id (with or without hyphens)."""
    clean = (page_id or "").replace("-", "")
    if not clean:
        return ""
    return f"https://www.notion.so/{clean}"


class NotionClient:
    """Notion API client with rate-limit retry and payload validation."""

    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self, token: str) -> None:
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": self.API_VERSION,
            "Content-Type": "application/json",
        }
        self._httpx: Any = None
        self._client: Any = None

    def _get_httpx(self) -> Any:
        if self._httpx is None:
            try:
                import httpx as _httpx

                self._httpx = _httpx
            except ImportError:
                raise ImportError("notion tool requires 'httpx'. Install with: pip install httpx") from None
        return self._httpx

    def _get_client(self) -> Any:
        """Return a reusable httpx.Client (lazy singleton)."""
        if self._client is None:
            httpx = self._get_httpx()
            self._client = httpx.Client(timeout=30.0, headers=self._headers)
        return self._client

    def _request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict | list:
        """Send HTTP request with rate-limit retry and payload validation."""
        url = f"{self.BASE_URL}{endpoint}"

        if json_data is not None:
            payload_str = json.dumps(json_data, ensure_ascii=False)
            if len(payload_str.encode("utf-8")) > MAX_PAYLOAD_BYTES:
                raise NotionAPIError(
                    t(
                        "notion.payload_too_large",
                        max_bytes=MAX_PAYLOAD_BYTES,
                        actual_bytes=len(payload_str.encode("utf-8")),
                    )
                )

        def _do_request() -> dict | list:
            client = self._get_client()
            resp = client.request(
                method,
                url,
                json=json_data,
                params=params,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", RATE_LIMIT_WAIT_DEFAULT))
                raise RateLimitError(retry_after, resp)
            if 500 <= resp.status_code < 600:
                raise ServerError(resp.status_code, resp.text[:500])
            resp.raise_for_status()
            if not resp.text.strip():
                return {}
            return resp.json()

        def _get_retry_after(exc: Exception) -> float | None:
            if isinstance(exc, RateLimitError):
                return exc.retry_after
            return None

        return retry_on_rate_limit(
            _do_request,
            max_retries=RATE_LIMIT_RETRY_MAX,
            default_wait=RATE_LIMIT_WAIT_DEFAULT,
            get_retry_after=_get_retry_after,
            retry_on=(RateLimitError,),
        )

    def search(
        self,
        query: str = "",
        filter: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> dict:
        """POST /v1/search."""
        body: dict[str, Any] = {"page_size": page_size}
        if query:
            body["query"] = query
        if filter:
            body["filter"] = filter
        if sort:
            body["sort"] = sort
        if start_cursor:
            body["start_cursor"] = start_cursor
        return self._request("POST", "/search", json_data=body)

    def get_page(self, page_id: str) -> dict:
        """GET /v1/pages/{page_id}."""
        return self._request("GET", f"/pages/{page_id}")

    def get_page_content(
        self,
        page_id: str,
        page_size: int = 100,
    ) -> dict:
        """GET /v1/blocks/{page_id}/children (paginated), convert to markdown."""
        all_blocks: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": page_size}
            if start_cursor:
                params["start_cursor"] = start_cursor
            data = self._request(
                "GET",
                f"/blocks/{page_id}/children",
                params=params,
            )
            blocks = data.get("results", [])
            all_blocks.extend(blocks)
            has_more = data.get("has_more", False)
            if not has_more:
                break
            start_cursor = data.get("next_cursor")
            if not start_cursor:
                break

        # Fetch children for blocks with has_children (table, toggle, etc.)
        for block in all_blocks:
            if block.get("has_children"):
                bid = block.get("id", "")
                child_blocks: list[dict] = []
                ccursor: str | None = None
                while True:
                    cparams: dict[str, Any] = {"page_size": 100}
                    if ccursor:
                        cparams["start_cursor"] = ccursor
                    cdata = self._request(
                        "GET",
                        f"/blocks/{bid}/children",
                        params=cparams,
                    )
                    child_blocks.extend(cdata.get("results", []))
                    if not cdata.get("has_more"):
                        break
                    ccursor = cdata.get("next_cursor")
                    if not ccursor:
                        break
                block["_children"] = child_blocks

        markdown = blocks_to_markdown(all_blocks)
        return {
            "page_id": page_id,
            "markdown": markdown,
            "blocks_count": len(all_blocks),
        }

    def get_database(self, database_id: str) -> dict:
        """GET /v1/databases/{database_id}."""
        return self._request("GET", f"/databases/{database_id}")

    def query_database(
        self,
        database_id: str,
        filter: dict[str, Any] | None = None,
        sorts: list[dict[str, Any]] | None = None,
        page_size: int = 10,
        start_cursor: str | None = None,
    ) -> dict:
        """POST /v1/databases/{database_id}/query."""
        body: dict[str, Any] = {"page_size": page_size}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor
        return self._request("POST", f"/databases/{database_id}/query", json_data=body)

    def create_page(
        self,
        parent: dict[str, str],
        properties: dict[str, Any],
        children: list[dict[str, Any]] | None = None,
    ) -> dict:
        """POST /v1/pages. parent: {"database_id": "..."} or {"page_id": "..."}."""
        body: dict[str, Any] = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children
        return self._request("POST", "/pages", json_data=body)

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict:
        """PATCH /v1/pages/{page_id}."""
        return self._request("PATCH", f"/pages/{page_id}", json_data={"properties": properties})

    def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: dict[str, Any],
    ) -> dict:
        """POST /v1/databases."""
        body = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        return self._request("POST", "/databases", json_data=body)


# ── Credential resolution ────────────────────────────────


def _resolve_token(args: dict[str, Any]) -> str:
    """Resolve Notion token: per-Anima NOTION_API_TOKEN__{name} → shared."""
    anima_dir = args.get("anima_dir")
    if anima_dir:
        from core.tools._base import _lookup_shared_credentials, _lookup_vault_credential

        anima_name = Path(anima_dir).name
        per_key = f"NOTION_API_TOKEN__{anima_name}"
        token = _lookup_vault_credential(per_key)
        if token:
            logger.debug("Using per-Anima Notion token for '%s'", anima_name)
            return token
        token = _lookup_shared_credentials(per_key)
        if token:
            logger.debug("Using per-Anima Notion token for '%s'", anima_name)
            return token
    try:
        return get_credential("notion", "notion", env_var="NOTION_API_TOKEN")
    except ToolConfigError:
        raise ToolConfigError(t("notion.config_error")) from None


# ── Tool schemas & CLI ────────────────────────────────────


def get_tool_schemas() -> list[dict]:
    """Return Anthropic tool_use schemas. External tools use use_tool."""
    return []


def get_cli_guide() -> str:
    """Return CLI usage guide for Notion tools."""
    return """\
### Notion
```bash
animaworks-tool notion search [query] -j
animaworks-tool notion get-page <page_id> -j
animaworks-tool notion get-page-content <page_id> -j
animaworks-tool notion get-database <database_id> -j
animaworks-tool notion query <database_id> [--filter JSON] -j
animaworks-tool notion create-page --parent-page-id <id> --properties JSON -j
animaworks-tool notion update-page <page_id> --properties JSON -j
animaworks-tool notion create-database --parent-page-id <id> --title "..." --properties JSON -j
```"""


def cli_main(argv: list[str] | None = None) -> None:
    """Standalone CLI entry point for the Notion tool."""
    parser = argparse.ArgumentParser(
        prog="animaworks-notion",
        description=t("notion.cli_desc"),
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # search
    p = sub.add_parser("search", help="Search Notion")
    p.add_argument("query", nargs="*", help="Search query")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # get-page
    p = sub.add_parser("get-page", help="Get page metadata")
    p.add_argument("page_id", help="Page ID")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # get-page-content
    p = sub.add_parser("get-page-content", help="Get page content as markdown")
    p.add_argument("page_id", help="Page ID")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # get-database
    p = sub.add_parser("get-database", help="Get database metadata")
    p.add_argument("database_id", help="Database ID")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # query
    p = sub.add_parser("query", help="Query database")
    p.add_argument("database_id", help="Database ID")
    p.add_argument("--filter", help="Filter JSON")
    p.add_argument("--sorts", help="Sorts JSON array")
    p.add_argument("-n", "--page-size", type=int, default=10, help="Page size")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # create-page
    p = sub.add_parser("create-page", help="Create page")
    p.add_argument("--parent-page-id", help="Parent page ID")
    p.add_argument("--parent-database-id", help="Parent database ID")
    p.add_argument("--properties", required=True, help="Properties JSON")
    p.add_argument("--children", help="Children blocks JSON (optional)")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # update-page
    p = sub.add_parser("update-page", help="Update page")
    p.add_argument("page_id", help="Page ID")
    p.add_argument("--properties", required=True, help="Properties JSON")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    # create-database
    p = sub.add_parser("create-database", help="Create database")
    p.add_argument("--parent-page-id", required=True, help="Parent page ID")
    p.add_argument("--title", required=True, help="Database title")
    p.add_argument("--properties", required=True, help="Properties JSON")
    p.add_argument("-j", "--json", action="store_true", help="Output as JSON")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        token = _resolve_cli_token()
        client = NotionClient(token=token)
    except ToolConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        _run_cli_command(client, args)
    except NotionAPIError as e:
        print(f"Notion API error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


def _resolve_cli_token() -> str:
    """Resolve token for CLI (ANIMAWORKS_ANIMA_DIR env)."""
    import os

    args = {"anima_dir": os.environ.get("ANIMAWORKS_ANIMA_DIR")}
    return _resolve_token(args)


def _run_cli_command(client: NotionClient, args: argparse.Namespace) -> None:
    """Dispatch CLI subcommands."""
    out_json = getattr(args, "json", False)

    if args.command == "search":
        query = " ".join(getattr(args, "query", []) or [])
        result = client.search(query=query, page_size=20)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            for item in result.get("results", []):
                obj = item.get("object", "")
                tid = item.get("id", "")
                if obj == "page":
                    title = "Untitled"
                    props = item.get("properties", {})
                    for _k, v in props.items():
                        if isinstance(v, dict) and v.get("type") == "title":
                            tarr = v.get("title", [])
                            if tarr:
                                title = tarr[0].get("plain_text", "Untitled")
                            break
                    print(f"Page: {title} ({build_page_url(tid)})")
                elif obj == "database":
                    title_arr = item.get("title", [])
                    title = title_arr[0].get("plain_text", "Untitled") if title_arr else "Untitled"
                    print(f"Database: {title} ({tid})")

    elif args.command == "get-page":
        result = client.get_page(args.page_id)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    elif args.command == "get-page-content":
        result = client.get_page_content(args.page_id)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(result.get("markdown", ""))

    elif args.command == "get-database":
        result = client.get_database(args.database_id)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    elif args.command == "query":
        filter_obj = None
        if getattr(args, "filter", None):
            filter_obj = json.loads(args.filter)
        sorts_obj = None
        if getattr(args, "sorts", None):
            sorts_obj = json.loads(args.sorts)
        result = client.query_database(
            args.database_id,
            filter=filter_obj,
            sorts=sorts_obj,
            page_size=getattr(args, "page_size", 10),
        )
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            for row in result.get("results", []):
                print(json.dumps(row, ensure_ascii=False, default=str))

    elif args.command == "create-page":
        parent_page_id = getattr(args, "parent_page_id", None)
        parent_database_id = getattr(args, "parent_database_id", None)
        if not parent_page_id and not parent_database_id:
            print(t("notion.parent_required"), file=sys.stderr)
            sys.exit(1)
        parent: dict[str, str] = (
            {"type": "page_id", "page_id": parent_page_id}
            if parent_page_id
            else {"type": "database_id", "database_id": parent_database_id}
        )
        properties = json.loads(args.properties)
        children = None
        if getattr(args, "children", None):
            children = json.loads(args.children)
        result = client.create_page(parent=parent, properties=properties, children=children)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"Created: {build_page_url(result.get('id', ''))}")

    elif args.command == "update-page":
        properties = json.loads(args.properties)
        result = client.update_page(args.page_id, properties)
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"Updated: {build_page_url(args.page_id)}")

    elif args.command == "create-database":
        properties = json.loads(args.properties)
        result = client.create_database(
            parent_page_id=args.parent_page_id,
            title=args.title,
            properties=properties,
        )
        if out_json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"Created database: {result.get('id', '')}")


# ── Dispatch ──────────────────────────────────────────────


def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Dispatch a tool call by schema name."""
    token = _resolve_token(args)
    client = NotionClient(token=token)

    if name == "notion_search":
        return client.search(
            query=args.get("query", ""),
            filter=args.get("filter"),
            sort=args.get("sort"),
            page_size=args.get("page_size", 10),
            start_cursor=args.get("start_cursor"),
        )
    if name == "notion_get_page":
        page_id = args.get("page_id")
        if not page_id:
            raise ValueError(t("notion.page_id_required"))
        return client.get_page(page_id)
    if name == "notion_get_page_content":
        page_id = args.get("page_id")
        if not page_id:
            raise ValueError(t("notion.page_id_required"))
        return client.get_page_content(page_id, page_size=args.get("page_size", 100))
    if name == "notion_get_database":
        database_id = args.get("database_id")
        if not database_id:
            raise ValueError(t("notion.database_id_required"))
        return client.get_database(database_id)
    if name == "notion_query":
        database_id = args.get("database_id")
        if not database_id:
            raise ValueError(t("notion.database_id_required"))
        return client.query_database(
            database_id,
            filter=args.get("filter"),
            sorts=args.get("sorts"),
            page_size=args.get("page_size", 10),
            start_cursor=args.get("start_cursor"),
        )
    if name == "notion_create_page":
        parent_page_id = args.get("parent_page_id")
        parent_database_id = args.get("parent_database_id")
        if not parent_page_id and not parent_database_id:
            raise ValueError(t("notion.parent_required"))
        parent = (
            {"type": "page_id", "page_id": parent_page_id}
            if parent_page_id
            else {"type": "database_id", "database_id": parent_database_id}
        )
        return client.create_page(
            parent=parent,
            properties=args.get("properties", {}),
            children=args.get("children"),
        )
    if name == "notion_update_page":
        page_id = args.get("page_id")
        if not page_id:
            raise ValueError(t("notion.page_id_required"))
        return client.update_page(page_id, args.get("properties", {}))
    if name == "notion_create_database":
        parent_page_id = args.get("parent_page_id")
        if not parent_page_id:
            raise ValueError(t("notion.parent_page_id_required"))
        return client.create_database(
            parent_page_id=parent_page_id,
            title=args.get("title", ""),
            properties=args.get("properties", {}),
        )
    raise ValueError(t("notion.unknown_action", name=name))


if __name__ == "__main__":
    cli_main()
