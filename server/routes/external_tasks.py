from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""External tasks widget API — MVP with mock data."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("animaworks.routes.external_tasks")

# ── Constants ────────────────────────────────────


class SourceType(StrEnum):
    GITHUB = "github"
    SLACK = "slack"
    GMAIL = "gmail"
    JIRA = "jira"
    NOTION = "notion"
    OTHER = "other"


class TaskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


VALID_SORT_KEYS = {"priority", "created_at", "last_updated_at"}
VALID_ORDER = {"asc", "desc"}


# ── Response models ──────────────────────────────


class ExternalTaskItem(BaseModel):
    id: str
    title: str
    status: str
    source_type: str
    source_icon: str
    source_url: str | None = None
    created_at: str
    last_updated_at: str
    priority: int


class PaginationMeta(BaseModel):
    total_count: int
    limit: int
    offset: int
    has_more: bool


class ExternalTasksResponse(BaseModel):
    data: list[ExternalTaskItem]
    meta: PaginationMeta


class ErrorDetail(BaseModel):
    field: str
    value: str
    constraint: str | None = None
    allowed: list[str] | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str | None = None
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ── Mock data ────────────────────────────────────


def _generate_mock_tasks() -> list[dict]:
    """Generate realistic mock external tasks for MVP."""
    now = datetime.now(UTC)
    return [
        {
            "id": "ext-task-001",
            "title": "GitHub PR #142 のレビュー依頼",
            "status": "open",
            "source_type": "github",
            "source_icon": "github",
            "source_url": "https://github.com/org/repo/pull/142",
            "created_at": (now - timedelta(hours=6)).isoformat(),
            "last_updated_at": (now - timedelta(minutes=30)).isoformat(),
            "priority": 90,
        },
        {
            "id": "ext-task-002",
            "title": "Slack #ops: 本番デプロイ承認待ち",
            "status": "open",
            "source_type": "slack",
            "source_icon": "slack",
            "source_url": "https://app.slack.com/client/T0001/C0001",
            "created_at": (now - timedelta(hours=4)).isoformat(),
            "last_updated_at": (now - timedelta(hours=1)).isoformat(),
            "priority": 80,
        },
        {
            "id": "ext-task-003",
            "title": "Gmail: クライアントA 見積もり確認依頼",
            "status": "open",
            "source_type": "gmail",
            "source_icon": "gmail",
            "source_url": None,
            "created_at": (now - timedelta(hours=8)).isoformat(),
            "last_updated_at": (now - timedelta(hours=2)).isoformat(),
            "priority": 70,
        },
        {
            "id": "ext-task-004",
            "title": "Notion: Sprint 5 計画ドキュメントレビュー",
            "status": "in_progress",
            "source_type": "notion",
            "source_icon": "notion",
            "source_url": "https://notion.so/page/abc123",
            "created_at": (now - timedelta(days=1)).isoformat(),
            "last_updated_at": (now - timedelta(hours=3)).isoformat(),
            "priority": 60,
        },
        {
            "id": "ext-task-005",
            "title": "Jira: PROJ-456 バグ修正",
            "status": "open",
            "source_type": "jira",
            "source_icon": "jira",
            "source_url": "https://jira.example.com/browse/PROJ-456",
            "created_at": (now - timedelta(days=2)).isoformat(),
            "last_updated_at": (now - timedelta(hours=5)).isoformat(),
            "priority": 85,
        },
        {
            "id": "ext-task-006",
            "title": "GitHub Issue #89: パフォーマンス改善提案",
            "status": "open",
            "source_type": "github",
            "source_icon": "github",
            "source_url": "https://github.com/org/repo/issues/89",
            "created_at": (now - timedelta(days=3)).isoformat(),
            "last_updated_at": (now - timedelta(days=1)).isoformat(),
            "priority": 50,
        },
        {
            "id": "ext-task-007",
            "title": "Slack #general: 週次MTGアジェンダ確認",
            "status": "done",
            "source_type": "slack",
            "source_icon": "slack",
            "source_url": None,
            "created_at": (now - timedelta(days=4)).isoformat(),
            "last_updated_at": (now - timedelta(days=2)).isoformat(),
            "priority": 30,
        },
        {
            "id": "ext-task-008",
            "title": "外部連携テストタスク",
            "status": "cancelled",
            "source_type": "other",
            "source_icon": "other",
            "source_url": None,
            "created_at": (now - timedelta(days=5)).isoformat(),
            "last_updated_at": (now - timedelta(days=3)).isoformat(),
            "priority": 10,
        },
    ]


# ── Helpers ──────────────────────────────────────


def _error_response(status_code: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body: dict = {"error": {"code": code, "message": message}}
    if status_code >= 500:
        body["error"]["trace_id"] = str(uuid.uuid4())[:12]
    if details:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


# ── Router ───────────────────────────────────────


def create_external_tasks_router() -> APIRouter:
    router = APIRouter(tags=["external-tasks"])

    @router.get("/external-tasks")
    async def get_external_tasks(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        status: str | None = Query(default=None),
        source_type: str | None = Query(default=None),
        since: str | None = Query(default=None),
        sort: str = Query(default="priority"),
        order: str = Query(default="desc"),
    ):
        """Get external tasks for the widget. MVP uses mock data."""

        # Validate sort key
        if sort not in VALID_SORT_KEYS:
            return _error_response(
                400,
                "INVALID_PARAMETER",
                f"Invalid value for 'sort': must be one of {', '.join(VALID_SORT_KEYS)}.",
                [{"field": "sort", "value": sort, "allowed": list(VALID_SORT_KEYS)}],
            )

        # Validate order
        if order not in VALID_ORDER:
            return _error_response(
                400,
                "INVALID_PARAMETER",
                "Invalid value for 'order': must be 'asc' or 'desc'.",
                [{"field": "order", "value": order, "allowed": list(VALID_ORDER)}],
            )

        # Parse status filter
        status_filter: set[str] | None = None
        if status:
            status_values = {s.strip() for s in status.split(",")}
            valid_statuses = {e.value for e in TaskStatus}
            invalid = status_values - valid_statuses
            if invalid:
                return _error_response(
                    422,
                    "INVALID_FILTER",
                    f"Unknown status: '{', '.join(invalid)}'. Allowed values: {', '.join(sorted(valid_statuses))}.",
                    [{"field": "status", "value": status, "allowed": sorted(valid_statuses)}],
                )
            status_filter = status_values

        # Parse source_type filter
        source_filter: set[str] | None = None
        if source_type:
            source_values = {s.strip() for s in source_type.split(",")}
            valid_sources = {e.value for e in SourceType}
            invalid = source_values - valid_sources
            if invalid:
                return _error_response(
                    422,
                    "INVALID_FILTER",
                    f"Unknown source_type: '{', '.join(invalid)}'. Allowed values: {', '.join(sorted(valid_sources))}.",
                    [{"field": "source_type", "value": source_type, "allowed": sorted(valid_sources)}],
                )
            source_filter = source_values

        # Parse since filter
        since_dt: datetime | None = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                return _error_response(
                    400,
                    "INVALID_PARAMETER",
                    "Invalid value for 'since': must be ISO 8601 format.",
                    [{"field": "since", "value": since, "constraint": "ISO 8601"}],
                )

        # Get mock data
        tasks = _generate_mock_tasks()

        # Apply filters
        if status_filter:
            tasks = [t for t in tasks if t["status"] in status_filter]
        if source_filter:
            tasks = [t for t in tasks if t["source_type"] in source_filter]
        if since_dt:
            tasks = [t for t in tasks if datetime.fromisoformat(t["last_updated_at"]) >= since_dt]

        # Sort
        reverse = order == "desc"
        sort_key = sort
        if sort_key == "priority":
            tasks.sort(key=lambda t: (t["priority"], t["created_at"]), reverse=reverse)
        else:
            tasks.sort(key=lambda t: t.get(sort_key, ""), reverse=reverse)

        total_count = len(tasks)

        # Paginate
        paginated = tasks[offset : offset + limit]
        has_more = (offset + limit) < total_count

        return {
            "data": paginated,
            "meta": {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
            },
        }

    return router
