from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""AI Brainstorm API — multi-character perspective brainstorming with LLM."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.i18n import t

logger = logging.getLogger("animaworks.routes.brainstorm")

# ── Character Presets ─────────────────────────────────────────

CHARACTERS = [
    {
        "id": "realist",
        "name_key": "brainstorm.char.realist",
        "desc_key": "brainstorm.char.realist.desc",
        "icon": "chart-line",
        "system_prompt_key": "brainstorm.char.realist.prompt",
    },
    {
        "id": "challenger",
        "name_key": "brainstorm.char.challenger",
        "desc_key": "brainstorm.char.challenger.desc",
        "icon": "rocket",
        "system_prompt_key": "brainstorm.char.challenger.prompt",
    },
    {
        "id": "customer",
        "name_key": "brainstorm.char.customer",
        "desc_key": "brainstorm.char.customer.desc",
        "icon": "heart",
        "system_prompt_key": "brainstorm.char.customer.prompt",
    },
    {
        "id": "engineer",
        "name_key": "brainstorm.char.engineer",
        "desc_key": "brainstorm.char.engineer.desc",
        "icon": "wrench",
        "system_prompt_key": "brainstorm.char.engineer.prompt",
    },
]

CHARACTER_MAP = {c["id"]: c for c in CHARACTERS}

# ── Request / Response models ─────────────────────────────────


class BrainstormRequest(BaseModel):
    theme: str = Field(..., min_length=1, max_length=2000)
    constraints: str = Field(default="", max_length=2000)
    expected_output: str = Field(default="", max_length=2000)
    character_ids: list[str] = Field(default_factory=lambda: [c["id"] for c in CHARACTERS])
    model: str = ""


# ── Helpers ───────────────────────────────────────────────────


def _resolve_model() -> str:
    try:
        from core.config import load_config

        return load_config().consolidation.llm_model
    except Exception:
        return ""


def _available_models() -> list[dict[str, str]]:
    try:
        from core.config import load_config

        cfg = load_config()
    except Exception:
        return []

    models: list[dict[str, str]] = []
    seen: set[str] = set()

    default = cfg.consolidation.llm_model
    if default and default not in seen:
        label = default.split("/")[-1] if "/" in default else default
        models.append({"id": default, "label": label})
        seen.add(default)

    for provider, cred in cfg.credentials.items():
        if not cred.api_key:
            continue
        if provider == "anthropic":
            for m in ("anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5"):
                if m not in seen:
                    models.append({"id": m, "label": m.split("/")[-1]})
                    seen.add(m)
        elif provider == "openai":
            for m in ("openai/gpt-4.1-mini", "openai/gpt-4.1-nano"):
                if m not in seen:
                    models.append({"id": m, "label": m.split("/")[-1]})
                    seen.add(m)
        elif provider in ("google", "gemini"):
            for m in ("gemini/gemini-2.5-flash",):
                if m not in seen:
                    models.append({"id": m, "label": m.split("/")[-1]})
                    seen.add(m)

    return models


async def _generate_character_proposal(
    character: dict[str, Any],
    theme: str,
    constraints: str,
    expected_output: str,
    model: str,
) -> dict[str, Any]:
    """Generate a single character's brainstorm proposal."""
    try:
        from core.memory._llm_utils import one_shot_completion
    except ImportError:
        return {
            "character_id": character["id"],
            "error": "LLM not available",
            "proposal": None,
        }

    system_prompt = t(character["system_prompt_key"])
    user_prompt = t(
        "brainstorm.user_prompt",
        theme=theme,
        constraints=constraints or t("brainstorm.no_constraints"),
        expected_output=expected_output or t("brainstorm.no_expected_output"),
    )

    try:
        result = await one_shot_completion(
            user_prompt,
            system_prompt=system_prompt,
            model=model,
            max_tokens=2048,
        )
        return {
            "character_id": character["id"],
            "proposal": result,
            "error": None,
        }
    except Exception as e:
        logger.warning("Brainstorm generation failed for %s: %s", character["id"], e)
        return {
            "character_id": character["id"],
            "proposal": None,
            "error": str(e),
        }


async def _synthesize_proposals(
    theme: str,
    proposals: list[dict[str, Any]],
    model: str,
) -> str | None:
    """Synthesize all character proposals into a formatted brainstorm result."""
    try:
        from core.memory._llm_utils import one_shot_completion
    except ImportError:
        return None

    char_sections = []
    for p in proposals:
        if p["proposal"]:
            char_name = t(CHARACTER_MAP[p["character_id"]]["name_key"])
            char_sections.append(f"### {char_name}\n{p['proposal']}")

    if not char_sections:
        return None

    combined = "\n\n".join(char_sections)
    system_prompt = t("brainstorm.synthesizer_prompt")
    user_prompt = t(
        "brainstorm.synthesizer_user_prompt",
        theme=theme,
        proposals=combined,
    )

    try:
        return await one_shot_completion(
            user_prompt,
            system_prompt=system_prompt,
            model=model,
            max_tokens=3000,
        )
    except Exception as e:
        logger.warning("Brainstorm synthesis failed: %s", e)
        return None


# ── Router ────────────────────────────────────────────────────


def create_brainstorm_router() -> APIRouter:
    router = APIRouter(prefix="/brainstorm", tags=["brainstorm"])

    @router.get("/characters")
    async def get_characters() -> JSONResponse:
        chars = []
        for c in CHARACTERS:
            chars.append(
                {
                    "id": c["id"],
                    "name": t(c["name_key"]),
                    "description": t(c["desc_key"]),
                    "icon": c["icon"],
                }
            )
        return JSONResponse({"characters": chars})

    @router.get("/models")
    async def get_models() -> JSONResponse:
        return JSONResponse(
            {
                "default_model": _resolve_model(),
                "available_models": _available_models(),
            }
        )

    @router.post("/generate")
    async def generate_brainstorm(req: BrainstormRequest) -> JSONResponse:
        # Validate characters
        valid_ids = {c["id"] for c in CHARACTERS}
        selected = [cid for cid in req.character_ids if cid in valid_ids]
        if not selected:
            return JSONResponse(
                {"error": t("brainstorm.no_characters_selected")},
                status_code=400,
            )

        model = req.model or _resolve_model()
        if not model:
            return JSONResponse(
                {"error": t("brainstorm.no_model_configured")},
                status_code=400,
            )

        if req.model:
            allowed = {m["id"] for m in _available_models()}
            if req.model not in allowed:
                return JSONResponse(
                    {"error": t("brainstorm.invalid_model")},
                    status_code=400,
                )

        # Generate proposals in parallel
        selected_chars = [CHARACTER_MAP[cid] for cid in selected]
        tasks = [
            _generate_character_proposal(char, req.theme, req.constraints, req.expected_output, model)
            for char in selected_chars
        ]
        proposals = await asyncio.gather(*tasks)

        # Synthesize
        synthesis = await _synthesize_proposals(req.theme, list(proposals), model)

        return JSONResponse(
            {
                "theme": req.theme,
                "model": model,
                "proposals": [
                    {
                        "character_id": p["character_id"],
                        "character_name": t(CHARACTER_MAP[p["character_id"]]["name_key"]),
                        "proposal": p["proposal"],
                        "error": p["error"],
                    }
                    for p in proposals
                ],
                "synthesis": synthesis,
            }
        )

    return router
