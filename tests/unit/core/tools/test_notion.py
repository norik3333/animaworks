# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.tools.notion."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.tools._base import ToolConfigError
from core.tools.notion import (
    EXECUTION_PROFILE,
    NotionAPIError,
    NotionClient,
    RateLimitError,
    ServerError,
    blocks_to_markdown,
    build_page_url,
    dispatch,
    get_tool_schemas,
)

# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client for NotionClient tests."""
    mock_instance = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "{}"
    mock_response.headers = {}
    mock_response.json.return_value = {}
    mock_response.raise_for_status = MagicMock()
    mock_instance.request.return_value = mock_response
    yield mock_instance, mock_response


@pytest.fixture
def notion_client(mock_httpx_client):
    """Pre-configured NotionClient with mocked httpx via _get_client()."""
    mock_instance, _mock_response = mock_httpx_client
    client = NotionClient(token="test-token")
    mock_httpx_module = MagicMock()
    mock_httpx_module.Client.return_value = mock_instance
    client._httpx = mock_httpx_module
    client._client = mock_instance
    return client


# ── TestBuildPageUrl ────────────────────────────────────────


class TestBuildPageUrl:
    """Tests for build_page_url()."""

    def test_normal_page_id(self) -> None:
        assert build_page_url("abc123def456") == "https://www.notion.so/abc123def456"

    def test_page_id_with_hyphens_stripped(self) -> None:
        assert build_page_url("abc-123-def-456") == "https://www.notion.so/abc123def456"

    def test_empty_string_returns_empty(self) -> None:
        assert build_page_url("") == ""

    def test_none_like_empty(self) -> None:
        assert build_page_url("") == ""


# ── TestBlocksToMarkdown ─────────────────────────────────────


class TestBlocksToMarkdown:
    """Tests for blocks_to_markdown() and _rich_text_to_markdown (indirect)."""

    def test_paragraph_block(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"plain_text": "Hello world", "type": "text"}],
                },
            },
        ]
        assert "Hello world" in blocks_to_markdown(blocks)

    def test_heading_1(self) -> None:
        blocks = [
            {
                "type": "heading_1",
                "heading_1": {"rich_text": [{"plain_text": "Title", "type": "text"}]},
            },
        ]
        assert "# Title" in blocks_to_markdown(blocks)

    def test_heading_2(self) -> None:
        blocks = [
            {
                "type": "heading_2",
                "heading_2": {"rich_text": [{"plain_text": "Subtitle", "type": "text"}]},
            },
        ]
        assert "## Subtitle" in blocks_to_markdown(blocks)

    def test_heading_3(self) -> None:
        blocks = [
            {
                "type": "heading_3",
                "heading_3": {"rich_text": [{"plain_text": "Section", "type": "text"}]},
            },
        ]
        assert "### Section" in blocks_to_markdown(blocks)

    def test_bulleted_list_item(self) -> None:
        blocks = [
            {
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"plain_text": "Item one", "type": "text"}],
                },
            },
        ]
        assert "- Item one" in blocks_to_markdown(blocks)

    def test_numbered_list_item(self) -> None:
        blocks = [
            {
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"plain_text": "First", "type": "text"}],
                },
            },
        ]
        assert "1. First" in blocks_to_markdown(blocks)

    def test_to_do_checked(self) -> None:
        blocks = [
            {
                "type": "to_do",
                "to_do": {
                    "checked": True,
                    "rich_text": [{"plain_text": "Done task", "type": "text"}],
                },
            },
        ]
        assert "- [x] Done task" in blocks_to_markdown(blocks)

    def test_to_do_unchecked(self) -> None:
        blocks = [
            {
                "type": "to_do",
                "to_do": {
                    "checked": False,
                    "rich_text": [{"plain_text": "Pending", "type": "text"}],
                },
            },
        ]
        assert "- [ ] Pending" in blocks_to_markdown(blocks)

    def test_code_block_with_language(self) -> None:
        blocks = [
            {
                "type": "code",
                "code": {
                    "language": "python",
                    "rich_text": [{"plain_text": "print(1)", "type": "text"}],
                },
            },
        ]
        md = blocks_to_markdown(blocks)
        assert "```python" in md
        assert "print(1)" in md
        assert "```" in md

    def test_quote_block(self) -> None:
        blocks = [
            {
                "type": "quote",
                "quote": {"rich_text": [{"plain_text": "A quote", "type": "text"}]},
            },
        ]
        assert "> A quote" in blocks_to_markdown(blocks)

    def test_callout_block_with_emoji(self) -> None:
        blocks = [
            {
                "type": "callout",
                "callout": {
                    "icon": {"emoji": "💡"},
                    "rich_text": [{"plain_text": "Tip", "type": "text"}],
                },
            },
        ]
        assert "> 💡 Tip" in blocks_to_markdown(blocks)

    def test_divider(self) -> None:
        blocks = [{"type": "divider", "divider": {}}]
        assert "---" in blocks_to_markdown(blocks)

    def test_image_block_external_url(self) -> None:
        blocks = [
            {
                "type": "image",
                "image": {
                    "type": "external",
                    "external": {"url": "https://example.com/img.png"},
                    "caption": [],
                },
            },
        ]
        assert "![image](https://example.com/img.png)" in blocks_to_markdown(blocks)

    def test_bookmark_block(self) -> None:
        blocks = [
            {
                "type": "bookmark",
                "bookmark": {"url": "https://example.com", "caption": []},
            },
        ]
        assert "[https://example.com](https://example.com)" in blocks_to_markdown(blocks)

    def test_link_preview_block(self) -> None:
        blocks = [
            {
                "type": "link_preview",
                "link_preview": {"url": "https://example.com"},
            },
        ]
        assert "[https://example.com](https://example.com)" in blocks_to_markdown(blocks)

    def test_table_block_with_table_row_children(self) -> None:
        blocks = [
            {
                "type": "table",
                "has_children": True,
                "_children": [
                    {
                        "type": "table_row",
                        "table_row": {
                            "cells": [
                                [{"plain_text": "A", "type": "text"}],
                                [{"plain_text": "B", "type": "text"}],
                            ],
                        },
                    },
                    {
                        "type": "table_row",
                        "table_row": {
                            "cells": [
                                [{"plain_text": "1", "type": "text"}],
                                [{"plain_text": "2", "type": "text"}],
                            ],
                        },
                    },
                ],
            },
        ]
        md = blocks_to_markdown(blocks)
        assert "| A | B |" in md or "| A | B |" in md.replace(" ", "")
        assert "---" in md

    def test_child_page(self) -> None:
        blocks = [
            {
                "type": "child_page",
                "child_page": {"title": "My Page"},
            },
        ]
        assert "📄 [My Page]" in blocks_to_markdown(blocks)

    def test_child_database(self) -> None:
        blocks = [
            {
                "type": "child_database",
                "child_database": {"title": "My DB"},
            },
        ]
        assert "📊 [My DB]" in blocks_to_markdown(blocks)

    def test_unknown_block_type_unsupported_comment(self) -> None:
        blocks = [{"type": "unknown_type", "unknown_type": {}}]
        assert "<!-- unsupported: unknown_type -->" in blocks_to_markdown(blocks)

    def test_blocks_in_trash_skipped(self) -> None:
        blocks = [
            {"type": "paragraph", "in_trash": True, "paragraph": {"rich_text": []}},
        ]
        assert blocks_to_markdown(blocks) == ""


# ── TestRichTextToMarkdown ──────────────────────────────────


class TestRichTextToMarkdown:
    """Tests for _rich_text_to_markdown via blocks_to_markdown."""

    def test_rich_text_bold(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "bold",
                            "type": "text",
                            "annotations": {"bold": True},
                        },
                    ],
                },
            },
        ]
        assert "**bold**" in blocks_to_markdown(blocks)

    def test_rich_text_italic(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "italic",
                            "type": "text",
                            "annotations": {"italic": True},
                        },
                    ],
                },
            },
        ]
        assert "*italic*" in blocks_to_markdown(blocks)

    def test_rich_text_strikethrough(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "strike",
                            "type": "text",
                            "annotations": {"strikethrough": True},
                        },
                    ],
                },
            },
        ]
        assert "~~strike~~" in blocks_to_markdown(blocks)

    def test_rich_text_code(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "code",
                            "type": "text",
                            "annotations": {"code": True},
                        },
                    ],
                },
            },
        ]
        assert "`code`" in blocks_to_markdown(blocks)

    def test_rich_text_link(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "link text",
                            "type": "text",
                            "href": "https://example.com",
                        },
                    ],
                },
            },
        ]
        assert "[link text](https://example.com)" in blocks_to_markdown(blocks)

    def test_mention_type_page(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "mention",
                            "mention": {"page": {"id": "abc-123-def"}},
                            "plain_text": "Page",
                        },
                    ],
                },
            },
        ]
        assert "[page](https://www.notion.so/abc123def)" in blocks_to_markdown(blocks)

    def test_mention_type_date(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "mention",
                            "mention": {"date": {"start": "2026-01-01"}},
                            "plain_text": "Date",
                        },
                    ],
                },
            },
        ]
        assert "2026-01-01" in blocks_to_markdown(blocks)

    def test_mention_type_date_with_end(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "mention",
                            "mention": {
                                "date": {"start": "2026-01-01", "end": "2026-01-31"},
                            },
                            "plain_text": "Range",
                        },
                    ],
                },
            },
        ]
        assert "2026-01-01 - 2026-01-31" in blocks_to_markdown(blocks)

    def test_mention_type_database(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "mention",
                            "mention": {"database": {}},
                            "plain_text": "DB",
                        },
                    ],
                },
            },
        ]
        assert "[database]" in blocks_to_markdown(blocks)

    def test_mention_type_user(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "mention",
                            "mention": {"user": {}},
                            "plain_text": "User",
                        },
                    ],
                },
            },
        ]
        assert "[user]" in blocks_to_markdown(blocks)

    def test_equation_type(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "equation",
                            "equation": {"expression": "E = mc^2"},
                            "plain_text": "E=mc",
                        },
                    ],
                },
            },
        ]
        assert "$E = mc^2$" in blocks_to_markdown(blocks)

    def test_empty_rich_text(self) -> None:
        blocks = [
            {
                "type": "paragraph",
                "paragraph": {"rich_text": []},
            },
        ]
        md = blocks_to_markdown(blocks)
        assert md.strip() == ""


# ── TestNotionClient ────────────────────────────────────────


class TestNotionClient:
    """Tests for NotionClient with mocked httpx."""

    def test_search_with_query(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"results": [], "has_more": false}'
        mock_resp.json.return_value = {"results": [], "has_more": False}

        result = notion_client.search(query="test query")

        assert result == {"results": [], "has_more": False}
        call = mock_instance.request.call_args
        assert call[0][0] == "POST"
        assert "/search" in call[0][1]
        body = call[1]["json"]
        assert body.get("query") == "test query"

    def test_get_page_normal(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "abc123"}'
        mock_resp.json.return_value = {"id": "abc123"}

        result = notion_client.get_page("abc-123-def")

        assert result == {"id": "abc123"}
        call = mock_instance.request.call_args
        assert call[0][0] == "GET"
        assert "/pages/abc-123-def" in call[0][1]

    def test_get_page_content_paginated_blocks_markdown(
        self,
        notion_client: NotionClient,
    ) -> None:
        mock_instance = notion_client._client

        first_page = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"plain_text": "Hi", "type": "text"}],
                    },
                    "has_children": False,
                },
            ],
            "has_more": True,
            "next_cursor": "cur2",
        }
        second_page = {"results": [], "has_more": False}

        def make_resp(data):
            m = MagicMock()
            m.status_code = 200
            m.headers = {}
            m.raise_for_status = MagicMock()
            m.json.return_value = data
            m.text = json.dumps(data)
            return m

        mock_instance.request.side_effect = [
            make_resp(first_page),
            make_resp(second_page),
        ]

        result = notion_client.get_page_content("page-id")

        assert "page_id" in result
        assert result["page_id"] == "page-id"
        assert "markdown" in result
        assert "Hi" in result["markdown"]
        assert result["blocks_count"] >= 1

    def test_get_database_normal(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "db123", "title": [{"plain_text": "My DB"}]}'
        mock_resp.json.return_value = {
            "id": "db123",
            "title": [{"plain_text": "My DB"}],
        }

        result = notion_client.get_database("db-123")

        assert result["id"] == "db123"
        call = mock_instance.request.call_args
        assert call[0][0] == "GET"
        assert "/databases/db-123" in call[0][1]

    def test_query_database_with_filter_and_sorts(
        self,
        notion_client: NotionClient,
    ) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"results": []}'
        mock_resp.json.return_value = {"results": []}

        result = notion_client.query_database(
            "db-id",
            filter={"property": "Status", "select": {"equals": "Done"}},
            sorts=[{"property": "Date", "direction": "descending"}],
        )

        assert result == {"results": []}
        call = mock_instance.request.call_args
        body = call[1]["json"]
        assert body.get("filter") == {"property": "Status", "select": {"equals": "Done"}}
        assert body.get("sorts") == [{"property": "Date", "direction": "descending"}]

    def test_create_page_with_page_parent(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "new-page"}'
        mock_resp.json.return_value = {"id": "new-page"}

        result = notion_client.create_page(
            parent={"type": "page_id", "page_id": "parent-123"},
            properties={"title": [{"text": {"content": "New Page"}}]},
        )

        assert result["id"] == "new-page"
        call = mock_instance.request.call_args
        body = call[1]["json"]
        assert body["parent"]["page_id"] == "parent-123"

    def test_create_page_with_database_parent(
        self,
        notion_client: NotionClient,
    ) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "new-page"}'
        mock_resp.json.return_value = {"id": "new-page"}

        result = notion_client.create_page(
            parent={"type": "database_id", "database_id": "db-123"},
            properties={"title": [{"text": {"content": "New"}}]},
        )

        assert result["id"] == "new-page"
        call = mock_instance.request.call_args
        body = call[1]["json"]
        assert body["parent"]["database_id"] == "db-123"

    def test_update_page_normal(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "page-1"}'
        mock_resp.json.return_value = {"id": "page-1"}

        result = notion_client.update_page(
            "page-1",
            properties={"title": [{"text": {"content": "Updated"}}]},
        )

        assert result["id"] == "page-1"
        call = mock_instance.request.call_args
        assert call[0][0] == "PATCH"
        assert "/pages/page-1" in call[0][1]

    def test_create_database_normal(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.text = '{"id": "db-new"}'
        mock_resp.json.return_value = {"id": "db-new"}

        result = notion_client.create_database(
            parent_page_id="parent-123",
            title="New DB",
            properties={"Name": {"title": {}}},
        )

        assert result["id"] == "db-new"
        call = mock_instance.request.call_args
        body = call[1]["json"]
        assert body["parent"]["page_id"] == "parent-123"
        assert body["title"][0]["text"]["content"] == "New DB"


# ── TestErrorHandling ───────────────────────────────────────


class TestErrorHandling:
    """Tests for error handling."""

    def test_429_raises_rate_limit_error_with_retry_after(
        self,
        notion_client: NotionClient,
    ) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "2"}
        mock_resp.text = "Rate limited"

        with patch("core.tools._retry.time.sleep"), pytest.raises(RateLimitError) as exc_info:
            notion_client.get_page("abc")

        assert exc_info.value.retry_after == 2.0
        assert exc_info.value.response is mock_resp

    def test_500_raises_server_error(self, notion_client: NotionClient) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with pytest.raises(ServerError) as exc_info:
            notion_client.get_page("abc")

        assert exc_info.value.status_code == 500
        assert "Internal" in exc_info.value.body or "500" in str(exc_info.value)

    def test_payload_too_large_raises_notion_api_error(
        self,
        notion_client: NotionClient,
    ) -> None:
        mock_instance = notion_client._client
        mock_resp = mock_instance.request.return_value
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        # Create a payload > 500_000 bytes
        large_props = {"x": "x" * 600_000}

        with pytest.raises(NotionAPIError) as exc_info:
            notion_client._request(
                "POST",
                "/pages",
                json_data={"parent": {"page_id": "x"}, "properties": large_props},
            )

        assert "500000" in str(exc_info.value) or "payload" in str(exc_info.value).lower()

    def test_httpx_not_installed_raises_import_error(self) -> None:
        import builtins

        client = NotionClient(token="test")
        client._httpx = None

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "httpx":
                raise ImportError("No module named 'httpx'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import), pytest.raises(ImportError, match="httpx"):
            client._get_httpx()


# ── TestCredentialResolution ────────────────────────────────


class TestCredentialResolution:
    """Tests for _resolve_token credential resolution."""

    def test_per_anima_token_found(self) -> None:
        from core.tools.notion import _resolve_token

        with (
            patch(
                "core.tools._base._lookup_vault_credential",
                return_value="per-anima-token",
            ) as mock_vault,
            patch("core.tools._base._lookup_shared_credentials"),
        ):
            result = _resolve_token({"anima_dir": "/tmp/animas/alice"})
            assert result == "per-anima-token"
            mock_vault.assert_called_once()
            assert mock_vault.call_args[0][0] == "NOTION_API_TOKEN__alice"

    def test_per_anima_not_found_shared_fallback(self) -> None:
        from core.tools.notion import _resolve_token

        with (
            patch("core.tools._base._lookup_vault_credential", return_value=None),
            patch(
                "core.tools._base._lookup_shared_credentials",
                return_value="shared-token",
            ),
        ):
            result = _resolve_token({"anima_dir": "/tmp/animas/alice"})
            assert result == "shared-token"

    def test_no_token_at_all_raises_tool_config_error(self) -> None:
        from core.tools.notion import _resolve_token

        with (
            patch("core.tools._base._lookup_vault_credential", return_value=None),
            patch("core.tools._base._lookup_shared_credentials", return_value=None),
            patch("core.tools.notion.get_credential", side_effect=ToolConfigError("missing")),
            pytest.raises(ToolConfigError, match="notion"),
        ):
            _resolve_token({"anima_dir": "/tmp/animas/alice"})


# ── TestDispatch ────────────────────────────────────────────


def _dispatch_test_helper(
    action: str,
    args: dict,
    expected_method: str,
    expected_call_args: dict | None = None,
) -> None:
    """Helper to test dispatch routes to correct client method."""
    with patch("core.tools.notion._resolve_token") as mock_resolve:
        mock_resolve.return_value = "token"
        with patch("core.tools.notion.NotionClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_method = getattr(mock_client, expected_method)
            mock_method.return_value = {"id": "abc"}

            result = dispatch(action, args)

            assert result == {"id": "abc"}
            mock_method.assert_called_once()
            if expected_call_args:
                call_kw = mock_method.call_args[1]
                for k, v in expected_call_args.items():
                    assert call_kw.get(k) == v


class TestDispatchActions:
    """Test each dispatch action routes correctly."""

    def test_notion_search(self) -> None:
        _dispatch_test_helper(
            "notion_search",
            {"query": "q", "page_size": 5},
            "search",
            {"query": "q", "page_size": 5},
        )

    def test_notion_get_page(self) -> None:
        _dispatch_test_helper(
            "notion_get_page",
            {"page_id": "pid-123"},
            "get_page",
        )

    def test_notion_get_page_content(self) -> None:
        _dispatch_test_helper(
            "notion_get_page_content",
            {"page_id": "pid-123", "page_size": 50},
            "get_page_content",
        )

    def test_notion_get_database(self) -> None:
        _dispatch_test_helper(
            "notion_get_database",
            {"database_id": "db-123"},
            "get_database",
        )

    def test_notion_query(self) -> None:
        _dispatch_test_helper(
            "notion_query",
            {"database_id": "db-123", "filter": {"x": 1}, "sorts": []},
            "query_database",
        )

    def test_notion_create_page_page_parent(self) -> None:
        _dispatch_test_helper(
            "notion_create_page",
            {
                "parent_page_id": "pid",
                "properties": {"title": []},
            },
            "create_page",
        )

    def test_notion_create_page_database_parent(self) -> None:
        _dispatch_test_helper(
            "notion_create_page",
            {
                "parent_database_id": "db-id",
                "properties": {"title": []},
            },
            "create_page",
        )

    def test_notion_update_page(self) -> None:
        _dispatch_test_helper(
            "notion_update_page",
            {"page_id": "pid", "properties": {}},
            "update_page",
        )

    def test_notion_create_database(self) -> None:
        _dispatch_test_helper(
            "notion_create_database",
            {
                "parent_page_id": "pid",
                "title": "DB",
                "properties": {},
            },
            "create_database",
        )


class TestDispatchValidationErrors:
    """Test dispatch raises ValueError for missing required args."""

    def test_missing_page_id_get_page(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="page_id"):
                dispatch("notion_get_page", {})

    def test_missing_page_id_get_page_content(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="page_id"):
                dispatch("notion_get_page_content", {})

    def test_missing_database_id(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="database_id"):
                dispatch("notion_get_database", {})

    def test_missing_parent_create_page(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="parent"):
                dispatch("notion_create_page", {"properties": {}})

    def test_missing_parent_page_id_create_database(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="parent_page_id"):
                dispatch(
                    "notion_create_database",
                    {"title": "T", "properties": {}},
                )

    def test_unknown_action_raises_value_error(self) -> None:
        with patch("core.tools.notion._resolve_token") as mock_resolve:
            mock_resolve.return_value = "token"
            with patch("core.tools.notion.NotionClient"), pytest.raises(ValueError, match="unknown"):
                dispatch("notion_unknown_action", {})


# ── TestGetToolSchemas ──────────────────────────────────────


class TestGetToolSchemas:
    """Tests for get_tool_schemas()."""

    def test_returns_empty_list(self) -> None:
        assert get_tool_schemas() == []


# ── TestExecutionProfile ────────────────────────────────────


class TestExecutionProfile:
    """Tests for EXECUTION_PROFILE."""

    def test_all_eight_actions_present(self) -> None:
        expected = {
            "search",
            "get_page",
            "get_page_content",
            "get_database",
            "query",
            "create_page",
            "update_page",
            "create_database",
        }
        assert set(EXECUTION_PROFILE.keys()) == expected

    def test_none_are_background_eligible(self) -> None:
        for action, profile in EXECUTION_PROFILE.items():
            assert profile.get("background_eligible") is False, f"{action} should not be background_eligible"


# ── TestCliMain ─────────────────────────────────────────────


class TestCliMain:
    """Tests for cli_main() and _run_cli_command()."""

    def test_cli_no_command_shows_help(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with pytest.raises(SystemExit) as exc_info:
            cli_main([])
        assert exc_info.value.code == 0

    def test_cli_search(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.search.return_value = {
                "results": [
                    {
                        "object": "page",
                        "id": "abc123",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Test Page"}],
                            },
                        },
                    },
                    {
                        "object": "database",
                        "id": "db123",
                        "title": [{"plain_text": "Test DB"}],
                    },
                ],
            }
            cli_main(["search", "test query"])
        out = capsys.readouterr().out
        assert "Test Page" in out
        assert "Test DB" in out

    def test_cli_search_json(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.search.return_value = {"results": []}
            cli_main(["search", "-j"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "results" in data

    def test_cli_get_page(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.get_page.return_value = {"id": "abc"}
            cli_main(["get-page", "abc", "-j"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["id"] == "abc"

    def test_cli_get_page_content_text(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.get_page_content.return_value = {
                "page_id": "abc",
                "markdown": "# Hello",
                "blocks_count": 1,
            }
            cli_main(["get-page-content", "abc"])
        out = capsys.readouterr().out
        assert "# Hello" in out

    def test_cli_get_database(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.get_database.return_value = {"id": "db1"}
            cli_main(["get-database", "db1", "-j"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["id"] == "db1"

    def test_cli_query(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.query_database.return_value = {"results": [{"id": "r1"}]}
            cli_main(["query", "db1", "--filter", '{"property": "Status"}', "-j"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data["results"]) == 1

    def test_cli_query_text(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.query_database.return_value = {"results": [{"id": "r1"}]}
            cli_main(["query", "db1"])
        out = capsys.readouterr().out
        assert "r1" in out

    def test_cli_create_page_with_page_parent(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.create_page.return_value = {"id": "new1"}
            cli_main(
                [
                    "create-page",
                    "--parent-page-id",
                    "parent1",
                    "--properties",
                    '{"Name": {"title": []}}',
                ]
            )
        out = capsys.readouterr().out
        assert "Created" in out

    def test_cli_create_page_with_db_parent(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.create_page.return_value = {"id": "new2"}
            cli_main(
                [
                    "create-page",
                    "--parent-database-id",
                    "db1",
                    "--properties",
                    '{"Name": {"title": []}}',
                    "-j",
                ]
            )
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["id"] == "new2"

    def test_cli_create_page_no_parent_exits(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient"),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli_main(["create-page", "--properties", "{}"])
            assert exc_info.value.code == 1

    def test_cli_update_page(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.update_page.return_value = {"id": "abc"}
            cli_main(["update-page", "abc", "--properties", '{"Status": {}}'])
        out = capsys.readouterr().out
        assert "Updated" in out

    def test_cli_create_database(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.create_database.return_value = {"id": "db_new"}
            cli_main(
                [
                    "create-database",
                    "--parent-page-id",
                    "p1",
                    "--title",
                    "My DB",
                    "--properties",
                    '{"Name": {"title": {}}}',
                ]
            )
        out = capsys.readouterr().out
        assert "Created database" in out

    def test_cli_notion_api_error_exits(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with (
            patch("core.tools.notion._resolve_cli_token", return_value="tok"),
            patch("core.tools.notion.NotionClient") as mock_cls,
        ):
            inst = mock_cls.return_value
            inst.search.side_effect = NotionAPIError("API failure")
            with pytest.raises(SystemExit) as exc_info:
                cli_main(["search", "test"])
            assert exc_info.value.code == 1

    def test_cli_tool_config_error_exits(self, capsys: pytest.CaptureFixture) -> None:
        from core.tools.notion import cli_main

        with patch("core.tools.notion._resolve_cli_token", side_effect=ToolConfigError("no token")):
            with pytest.raises(SystemExit) as exc_info:
                cli_main(["search", "test"])
            assert exc_info.value.code == 1


# ── TestGetClient ───────────────────────────────────────────


class TestGetClient:
    """Tests for _get_client() lazy singleton."""

    def test_get_client_creates_once(self) -> None:
        client = NotionClient(token="test-token")
        mock_httpx_mod = MagicMock()
        mock_http_client = MagicMock()
        mock_httpx_mod.Client.return_value = mock_http_client
        client._httpx = mock_httpx_mod

        c1 = client._get_client()
        c2 = client._get_client()
        assert c1 is c2
        mock_httpx_mod.Client.assert_called_once()


# ── TestGetCliGuide ─────────────────────────────────────────


class TestGetCliGuide:
    """Tests for get_cli_guide()."""

    def test_returns_non_empty_string(self) -> None:
        from core.tools.notion import get_cli_guide

        guide = get_cli_guide()
        assert isinstance(guide, str)
        assert "animaworks-tool notion" in guide
        assert "search" in guide


# ── TestBuildPageUrl edge cases ─────────────────────────────


class TestBuildPageUrlEdge:
    """Edge case tests for build_page_url."""

    def test_none_input(self) -> None:
        assert build_page_url(None) == ""  # type: ignore[arg-type]


# ── TestToggleWithChildren ──────────────────────────────────


class TestToggleWithChildren:
    """Tests for toggle block with _children."""

    def test_toggle_with_children(self) -> None:
        blocks = [
            {
                "type": "toggle",
                "toggle": {
                    "rich_text": [{"type": "text", "plain_text": "Click me"}],
                },
                "_children": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "plain_text": "Hidden content"}],
                        },
                    },
                ],
            },
        ]
        md = blocks_to_markdown(blocks)
        assert "Click me" in md
        assert "Hidden content" in md
        assert "<details>" in md
