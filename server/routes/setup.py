from __future__ import annotations
# AnimaWorks - Digital Person Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.

"""Setup wizard API routes for first-launch configuration."""

import asyncio
import json
import logging
import shutil
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("animaworks.routes.setup")

# ── Available providers ────────────────────────────────────
AVAILABLE_PROVIDERS = [
    {
        "id": "anthropic",
        "name": "Anthropic",
        "models": ["claude-sonnet-4-20250514", "claude-haiku-3.5-20241022"],
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "models": ["openai/gpt-4o", "openai/gpt-4o-mini"],
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "google",
        "name": "Google",
        "models": ["google/gemini-2.0-flash", "google/gemini-2.5-pro"],
        "env_key": "GOOGLE_API_KEY",
    },
    {
        "id": "ollama",
        "name": "Ollama (Local)",
        "models": ["ollama/gemma3:27b", "ollama/llama3.3:70b"],
        "env_key": None,
    },
]

AVAILABLE_LOCALES = ["ja", "en"]


# ── Request/Response models ────────────────────────────────


class ValidateKeyRequest(BaseModel):
    provider: str
    api_key: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, str]] = []
    api_key: str | None = None
    template: str | None = None
    locale: str = "ja"


class SetupCompleteRequest(BaseModel):
    locale: str = "ja"
    credentials: dict[str, dict[str, str]] = {}
    person: PersonSetup | None = None


class PersonSetup(BaseModel):
    name: str
    template: str | None = None
    identity_md: str | None = None


# ── Router factory ─────────────────────────────────────────


def create_setup_router() -> APIRouter:
    """Create the setup wizard API router."""
    router = APIRouter(prefix="/api/setup", tags=["setup"])

    # ── GET /api/setup/environment ──────────────────────────

    @router.get("/environment")
    async def get_environment(request: Request) -> dict[str, Any]:
        """Return environment information for the setup wizard."""
        from core.config import load_config

        config = load_config()
        claude_available = shutil.which("claude") is not None

        return {
            "claude_code_available": claude_available,
            "locale": config.locale,
            "providers": AVAILABLE_PROVIDERS,
            "available_locales": AVAILABLE_LOCALES,
        }

    # ── GET /api/setup/detect-locale ───────────────────────

    @router.get("/detect-locale")
    async def detect_locale(request: Request) -> dict[str, Any]:
        """Detect locale from Accept-Language header."""
        accept_lang = request.headers.get("accept-language", "")
        detected = _parse_accept_language(accept_lang)
        return {
            "detected": detected,
            "available": AVAILABLE_LOCALES,
        }

    # ── POST /api/setup/validate-key ───────────────────────

    @router.post("/validate-key")
    async def validate_key(body: ValidateKeyRequest) -> dict[str, Any]:
        """Validate an API key by making a small test request."""
        provider = body.provider
        api_key = body.api_key

        if provider == "anthropic":
            return await _validate_anthropic_key(api_key)
        elif provider == "openai":
            return await _validate_openai_key(api_key)
        elif provider == "google":
            return await _validate_google_key(api_key)
        elif provider == "ollama":
            return {"valid": True, "message": "Ollama does not require an API key"}
        else:
            return {"valid": False, "message": f"Unknown provider: {provider}"}

    # ── POST /api/setup/chat ───────────────────────────────

    @router.post("/chat")
    async def setup_chat(body: ChatRequest) -> StreamingResponse:
        """SSE streaming endpoint for character maker chat via LiteLLM."""
        return StreamingResponse(
            _stream_chat(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # ── GET /api/setup/templates ───────────────────────────

    @router.get("/templates")
    async def list_templates() -> dict[str, Any]:
        """Return available person templates."""
        from core.person_factory import list_person_templates

        templates = list_person_templates()
        return {"templates": templates}

    # ── POST /api/setup/complete ───────────────────────────

    @router.post("/complete")
    async def complete_setup(
        body: SetupCompleteRequest,
        request: Request,
    ) -> dict[str, Any]:
        """Finalize setup: save config, create person, mark complete."""
        from core.config import (
            AnimaWorksConfig,
            CredentialConfig,
            PersonModelConfig,
            invalidate_cache,
            load_config,
            save_config,
        )
        from core.paths import get_persons_dir

        config = load_config()

        # Update locale
        config.locale = body.locale

        # Update credentials
        for cred_name, cred_data in body.credentials.items():
            config.credentials[cred_name] = CredentialConfig(
                api_key=cred_data.get("api_key", ""),
                base_url=cred_data.get("base_url"),
            )

        # Create person if specified
        if body.person:
            persons_dir = get_persons_dir()
            person_name = body.person.name

            try:
                if body.person.template:
                    from core.person_factory import create_from_template

                    create_from_template(
                        persons_dir,
                        body.person.template,
                        person_name=person_name,
                    )
                else:
                    from core.person_factory import create_blank

                    person_dir = create_blank(persons_dir, person_name)
                    # If custom identity was provided, write it
                    if body.person.identity_md:
                        (person_dir / "identity.md").write_text(
                            body.person.identity_md, encoding="utf-8"
                        )

                config.persons[person_name] = PersonModelConfig()
                logger.info("Created person '%s' during setup", person_name)
            except FileExistsError:
                logger.warning("Person '%s' already exists, skipping creation", person_name)
            except Exception:
                logger.error("Failed to create person during setup", exc_info=True)
                return JSONResponse(
                    {"error": "Failed to create person"},
                    status_code=500,
                )

        # Mark setup as complete
        config.setup_complete = True
        save_config(config)
        invalidate_cache()

        # Update app state so the middleware switches behaviour immediately
        request.app.state.setup_complete = True

        logger.info("Setup completed successfully")
        return {"status": "ok", "message": "Setup complete. Reload to access the dashboard."}

    return router


# ── Helper functions ───────────────────────────────────────


def _parse_accept_language(header: str) -> str:
    """Parse Accept-Language header and return best matching locale.

    Supports weighted values like ``ja;q=0.9,en-US;q=0.8``.
    Returns the first match from AVAILABLE_LOCALES, or ``"ja"`` as fallback.
    """
    if not header:
        return "ja"

    # Parse entries: "ja;q=0.9,en-US;q=0.8,en;q=0.7"
    entries: list[tuple[float, str]] = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue
        if ";q=" in part:
            lang, _, q_str = part.partition(";q=")
            try:
                q = float(q_str.strip())
            except ValueError:
                q = 0.0
        else:
            lang = part
            q = 1.0
        # Normalise: "en-US" → "en"
        lang = lang.strip().split("-")[0].lower()
        entries.append((q, lang))

    # Sort by quality descending
    entries.sort(key=lambda e: e[0], reverse=True)

    for _q, lang in entries:
        if lang in AVAILABLE_LOCALES:
            return lang

    return "ja"


async def _validate_anthropic_key(api_key: str) -> dict[str, Any]:
    """Validate an Anthropic API key with a minimal request."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-3.5-20241022",
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
        if resp.status_code in (200, 201):
            return {"valid": True, "message": "API key is valid"}
        if resp.status_code == 401:
            return {"valid": False, "message": "Invalid API key"}
        return {"valid": False, "message": f"Unexpected status: {resp.status_code}"}
    except Exception as exc:
        return {"valid": False, "message": f"Connection error: {exc}"}


async def _validate_openai_key(api_key: str) -> dict[str, Any]:
    """Validate an OpenAI API key by listing models."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            return {"valid": True, "message": "API key is valid"}
        if resp.status_code == 401:
            return {"valid": False, "message": "Invalid API key"}
        return {"valid": False, "message": f"Unexpected status: {resp.status_code}"}
    except Exception as exc:
        return {"valid": False, "message": f"Connection error: {exc}"}


async def _validate_google_key(api_key: str) -> dict[str, Any]:
    """Validate a Google API key by listing models."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
            )
        if resp.status_code == 200:
            return {"valid": True, "message": "API key is valid"}
        if resp.status_code in (400, 401, 403):
            return {"valid": False, "message": "Invalid API key"}
        return {"valid": False, "message": f"Unexpected status: {resp.status_code}"}
    except Exception as exc:
        return {"valid": False, "message": f"Connection error: {exc}"}


async def _stream_chat(body: ChatRequest):
    """Generator that yields SSE events from LiteLLM streaming completion."""
    full_text = ""
    try:
        import litellm

        response = await litellm.acompletion(
            model=body.model,
            messages=body.messages,
            api_key=body.api_key,
            stream=True,
        )

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_text += delta.content
                yield f"event: text_delta\ndata: {json.dumps({'text': delta.content})}\n\n"
            # Small yield to allow event loop to process other tasks
            await asyncio.sleep(0)

        yield f"event: done\ndata: {json.dumps({'summary': full_text})}\n\n"
    except Exception as exc:
        logger.error("Chat streaming error: %s", exc)
        yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
