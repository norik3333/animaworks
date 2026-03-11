from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Team Presets API — industry × purpose templates for team builder."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.i18n import t

logger = logging.getLogger("animaworks.routes.team_presets")

# ── Industries ────────────────────────────────────────────────

INDUSTRIES = [
    {"id": "saas", "name_key": "preset.industry.saas"},
    {"id": "consulting", "name_key": "preset.industry.consulting"},
    {"id": "ec", "name_key": "preset.industry.ec"},
    {"id": "general", "name_key": "preset.industry.general"},
]

# ── Purposes ──────────────────────────────────────────────────

PURPOSES = [
    {"id": "new_development", "name_key": "preset.purpose.new_development"},
    {"id": "operations", "name_key": "preset.purpose.operations"},
    {"id": "research", "name_key": "preset.purpose.research"},
]

# ── Preset Definitions ───────────────────────────────────────

PRESETS = [
    {
        "id": "saas_dev",
        "name_key": "preset.saas_dev",
        "desc_key": "preset.saas_dev.desc",
        "industry": "saas",
        "purpose": "new_development",
        "recommended": True,
        "members": [
            {"roleId": "project_manager", "count": 1},
            {"roleId": "content_writer", "count": 1},
            {"roleId": "customer_support", "count": 1},
            {"roleId": "researcher", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.market_research", "role": "researcher"},
            {"title_key": "preset.task.competitor_analysis", "role": "researcher"},
            {"title_key": "preset.task.roadmap_draft", "role": "project_manager"},
            {"title_key": "preset.task.user_persona", "role": "content_writer"},
            {"title_key": "preset.task.onboarding_flow", "role": "customer_support"},
            {"title_key": "preset.task.kpi_setup", "role": "project_manager"},
            {"title_key": "preset.task.release_plan", "role": "project_manager"},
            {"title_key": "preset.task.faq_draft", "role": "customer_support"},
        ],
    },
    {
        "id": "saas_ops",
        "name_key": "preset.saas_ops",
        "desc_key": "preset.saas_ops.desc",
        "industry": "saas",
        "purpose": "operations",
        "recommended": False,
        "members": [
            {"roleId": "customer_support", "count": 2},
            {"roleId": "back_office", "count": 1},
            {"roleId": "secretary", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.ticket_triage", "role": "customer_support"},
            {"title_key": "preset.task.sla_monitor", "role": "customer_support"},
            {"title_key": "preset.task.report_weekly", "role": "back_office"},
            {"title_key": "preset.task.schedule_mgmt", "role": "secretary"},
            {"title_key": "preset.task.knowledge_base", "role": "customer_support"},
            {"title_key": "preset.task.escalation_flow", "role": "customer_support"},
            {"title_key": "preset.task.metrics_dashboard", "role": "back_office"},
            {"title_key": "preset.task.meeting_minutes", "role": "secretary"},
        ],
    },
    {
        "id": "consulting_dev",
        "name_key": "preset.consulting_dev",
        "desc_key": "preset.consulting_dev.desc",
        "industry": "consulting",
        "purpose": "new_development",
        "recommended": True,
        "members": [
            {"roleId": "project_manager", "count": 1},
            {"roleId": "researcher", "count": 1},
            {"roleId": "sales_assist", "count": 1},
            {"roleId": "content_writer", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.client_analysis", "role": "sales_assist"},
            {"title_key": "preset.task.proposal_draft", "role": "content_writer"},
            {"title_key": "preset.task.scope_definition", "role": "project_manager"},
            {"title_key": "preset.task.resource_plan", "role": "project_manager"},
            {"title_key": "preset.task.industry_report", "role": "researcher"},
            {"title_key": "preset.task.timeline_draft", "role": "project_manager"},
            {"title_key": "preset.task.risk_assessment", "role": "researcher"},
            {"title_key": "preset.task.kickoff_prep", "role": "project_manager"},
        ],
    },
    {
        "id": "consulting_research",
        "name_key": "preset.consulting_research",
        "desc_key": "preset.consulting_research.desc",
        "industry": "consulting",
        "purpose": "research",
        "recommended": False,
        "members": [
            {"roleId": "researcher", "count": 2},
            {"roleId": "content_writer", "count": 1},
            {"roleId": "project_manager", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.literature_review", "role": "researcher"},
            {"title_key": "preset.task.data_collection", "role": "researcher"},
            {"title_key": "preset.task.analysis_framework", "role": "researcher"},
            {"title_key": "preset.task.findings_report", "role": "content_writer"},
            {"title_key": "preset.task.stakeholder_briefing", "role": "project_manager"},
            {"title_key": "preset.task.trend_mapping", "role": "researcher"},
            {"title_key": "preset.task.benchmark_study", "role": "researcher"},
            {"title_key": "preset.task.exec_summary", "role": "content_writer"},
        ],
    },
    {
        "id": "ec_dev",
        "name_key": "preset.ec_dev",
        "desc_key": "preset.ec_dev.desc",
        "industry": "ec",
        "purpose": "new_development",
        "recommended": True,
        "members": [
            {"roleId": "project_manager", "count": 1},
            {"roleId": "customer_support", "count": 1},
            {"roleId": "sales_assist", "count": 1},
            {"roleId": "content_writer", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.product_catalog", "role": "content_writer"},
            {"title_key": "preset.task.pricing_strategy", "role": "sales_assist"},
            {"title_key": "preset.task.shipping_policy", "role": "project_manager"},
            {"title_key": "preset.task.cs_playbook", "role": "customer_support"},
            {"title_key": "preset.task.launch_checklist", "role": "project_manager"},
            {"title_key": "preset.task.promotion_plan", "role": "sales_assist"},
            {"title_key": "preset.task.return_policy", "role": "customer_support"},
            {"title_key": "preset.task.seo_plan", "role": "content_writer"},
        ],
    },
    {
        "id": "ec_ops",
        "name_key": "preset.ec_ops",
        "desc_key": "preset.ec_ops.desc",
        "industry": "ec",
        "purpose": "operations",
        "recommended": False,
        "members": [
            {"roleId": "customer_support", "count": 2},
            {"roleId": "back_office", "count": 1},
            {"roleId": "accounting", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.order_processing", "role": "back_office"},
            {"title_key": "preset.task.inventory_check", "role": "back_office"},
            {"title_key": "preset.task.customer_inquiry", "role": "customer_support"},
            {"title_key": "preset.task.review_response", "role": "customer_support"},
            {"title_key": "preset.task.sales_report", "role": "accounting"},
            {"title_key": "preset.task.refund_process", "role": "customer_support"},
            {"title_key": "preset.task.supplier_coord", "role": "back_office"},
            {"title_key": "preset.task.tax_filing", "role": "accounting"},
        ],
    },
    {
        "id": "general_dev",
        "name_key": "preset.general_dev",
        "desc_key": "preset.general_dev.desc",
        "industry": "general",
        "purpose": "new_development",
        "recommended": False,
        "members": [
            {"roleId": "project_manager", "count": 1},
            {"roleId": "secretary", "count": 1},
            {"roleId": "researcher", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.project_charter", "role": "project_manager"},
            {"title_key": "preset.task.stakeholder_map", "role": "project_manager"},
            {"title_key": "preset.task.meeting_setup", "role": "secretary"},
            {"title_key": "preset.task.background_research", "role": "researcher"},
            {"title_key": "preset.task.milestone_plan", "role": "project_manager"},
            {"title_key": "preset.task.comm_plan", "role": "secretary"},
            {"title_key": "preset.task.feasibility_study", "role": "researcher"},
            {"title_key": "preset.task.budget_draft", "role": "project_manager"},
        ],
    },
    {
        "id": "general_ops",
        "name_key": "preset.general_ops",
        "desc_key": "preset.general_ops.desc",
        "industry": "general",
        "purpose": "operations",
        "recommended": False,
        "members": [
            {"roleId": "secretary", "count": 1},
            {"roleId": "back_office", "count": 1},
            {"roleId": "accounting", "count": 1},
        ],
        "initial_tasks": [
            {"title_key": "preset.task.daily_ops_check", "role": "back_office"},
            {"title_key": "preset.task.document_mgmt", "role": "secretary"},
            {"title_key": "preset.task.expense_tracking", "role": "accounting"},
            {"title_key": "preset.task.vendor_mgmt", "role": "back_office"},
            {"title_key": "preset.task.calendar_coord", "role": "secretary"},
            {"title_key": "preset.task.monthly_close", "role": "accounting"},
            {"title_key": "preset.task.process_improvement", "role": "back_office"},
            {"title_key": "preset.task.compliance_check", "role": "accounting"},
        ],
    },
]


# ── Router ────────────────────────────────────────────────────


def create_team_presets_router() -> APIRouter:
    router = APIRouter(prefix="/team-presets", tags=["team-presets"])

    @router.get("/industries")
    async def get_industries() -> JSONResponse:
        return JSONResponse({"industries": [{"id": ind["id"], "name": t(ind["name_key"])} for ind in INDUSTRIES]})

    @router.get("/purposes")
    async def get_purposes() -> JSONResponse:
        return JSONResponse({"purposes": [{"id": p["id"], "name": t(p["name_key"])} for p in PURPOSES]})

    @router.get("")
    async def get_presets(
        industry: str | None = None,
        purpose: str | None = None,
    ) -> JSONResponse:
        results = PRESETS
        if industry:
            results = [p for p in results if p["industry"] == industry]
        if purpose:
            results = [p for p in results if p["purpose"] == purpose]

        return JSONResponse(
            {
                "presets": [
                    {
                        "id": p["id"],
                        "name": t(p["name_key"]),
                        "description": t(p["desc_key"]),
                        "industry": p["industry"],
                        "purpose": p["purpose"],
                        "recommended": p["recommended"],
                        "members": p["members"],
                        "initial_tasks": [
                            {
                                "title": t(task["title_key"]),
                                "role": task["role"],
                            }
                            for task in p["initial_tasks"]
                        ],
                        "member_count": sum(m["count"] for m in p["members"]),
                        "task_count": len(p["initial_tasks"]),
                    }
                    for p in results
                ]
            }
        )

    return router
