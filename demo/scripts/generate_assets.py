#!/usr/bin/env python3
"""Generate demo character assets using AnimaWorks image generation pipeline.

Usage:
    python demo/scripts/generate_assets.py [--preset PRESET] [--character NAME]
    python demo/scripts/generate_assets.py --preset ja-anime --character kaito

Requires NOVELAI_TOKEN and/or FAL_KEY environment variables.

Pipeline per style:
  anime:     NovelAI fullbody → Flux Kontext bustup/chibi
  realistic: Flux fullbody/bustup + shared chibi (no _realistic suffix)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DEMO_DIR.parent

sys.path.insert(0, str(PROJECT_ROOT))

# ── Preset definitions ────────────────────────────────────────

PRESETS: dict[str, dict[str, object]] = {
    "ja-anime": {
        "characters": ["kaito", "sora", "hina"],
        "supervisor": "kaito",
        "style": "anime",
    },
    "ja-business": {
        "characters": ["kaito", "sora", "hina"],
        "supervisor": "kaito",
        "style": "realistic",
    },
    "en-anime": {
        "characters": ["alex", "kai", "nova"],
        "supervisor": "alex",
        "style": "anime",
    },
    "en-business": {
        "characters": ["alex", "kai", "nova"],
        "supervisor": "alex",
        "style": "realistic",
    },
}


# ── Prompt extraction ─────────────────────────────────────────


_MALE_KEYWORDS = {"male", "男性", "男"}
_FEMALE_KEYWORDS = {"female", "女性", "女"}


def _extract_gender(md_path: Path) -> str:
    """Extract gender from character sheet (Gender/性別 field in table).

    Returns ``"male"`` or ``"female"``.  Defaults to ``"female"``
    when the field is absent or unrecognised.
    """
    text = md_path.read_text(encoding="utf-8")
    match = re.search(
        r"\|\s*(?:Gender|性別)\s*\|\s*(.+?)\s*\|",
        text,
        re.IGNORECASE,
    )
    if match:
        value = match.group(1).strip().lower()
        if value in _MALE_KEYWORDS:
            return "male"
        if value in _FEMALE_KEYWORDS:
            return "female"
    return "female"


def _extract_appearance(md_path: Path) -> str | None:
    """Extract appearance description from a character sheet markdown."""
    text = md_path.read_text(encoding="utf-8")

    patterns = [
        r"(?:image[_ ]?prompt|画像プロンプト)\s*[:\uff1a]\s*(.+)",
        r"(?:キャラクターデザイン|character[_ ]?design)\s*[:\uff1a]\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    section_pat = re.compile(
        r"^##\s+(?:外見|Appearance)\s*\n(.*?)(?=\n##|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = section_pat.search(text)
    if match:
        return match.group(1).strip()

    return None


def _build_prompt_for_style(appearance: str, style: str, gender: str = "female") -> str:
    """Convert appearance description to a generation prompt."""
    if style == "anime":
        tag = "1boy" if gender == "male" else "1girl"
        return (
            f"{tag}, {appearance}, full body, standing, white background, "
            "anime illustration, high quality, detailed"
        )
    person = "a young man" if gender == "male" else "a young woman"
    return (
        f"A professional photo of {person}: {appearance}. "
        "Full body, standing, studio lighting, neutral background, "
        "high quality photograph"
    )


# ── Generation ────────────────────────────────────────────────


def generate_character(
    preset_name: str,
    character_name: str,
    style: str,
    *,
    vibe_reference: bytes | None = None,
) -> bytes | None:
    """Generate all asset images for a single character.

    Args:
        vibe_reference: If provided, the fullbody is generated via Flux
            Kontext using this image as style reference (vibe transfer)
            instead of generating from scratch.

    Returns:
        The fullbody image bytes (used as vibe reference for subordinates).
    """
    preset_dir = DEMO_DIR / "presets" / preset_name
    md_path = preset_dir / "characters" / f"{character_name}.md"
    assets_dir = preset_dir / "assets" / character_name

    if not md_path.exists():
        print(f"  SKIP {character_name}: character sheet not found at {md_path}")
        return None

    appearance = _extract_appearance(md_path)
    if not appearance:
        print(f"  SKIP {character_name}: no appearance description found")
        return None

    gender = _extract_gender(md_path)
    prompt = _build_prompt_for_style(appearance, style, gender)
    print(f"  Prompt: {prompt[:120]}...")

    assets_dir.mkdir(parents=True, exist_ok=True)

    return _generate_with_clients(assets_dir, prompt, style, vibe_reference=vibe_reference)


def _generate_with_clients(
    assets_dir: Path,
    prompt: str,
    style: str,
    *,
    vibe_reference: bytes | None = None,
) -> bytes | None:
    """Generate images using the API clients directly.

    Returns:
        The fullbody image bytes.
    """
    from core.tools._image_clients import _CHIBI_PROMPT

    assets_dir.mkdir(parents=True, exist_ok=True)

    if style == "anime":
        fullbody_name = "avatar_fullbody.png"
        bustup_name = "avatar_bustup.png"
    else:
        fullbody_name = "avatar_fullbody_realistic.png"
        bustup_name = "avatar_bustup_realistic.png"
    chibi_name = "avatar_chibi.png"

    # ── Step 1: Full-body ──
    fullbody_path = assets_dir / fullbody_name
    fullbody_bytes: bytes | None = None

    if fullbody_path.exists() and fullbody_path.stat().st_size > 100:
        print("    fullbody: exists, skipping")
        fullbody_bytes = fullbody_path.read_bytes()
    elif vibe_reference is not None:
        if not os.environ.get("FAL_KEY"):
            print("    fullbody: SKIP (no FAL_KEY for vibe transfer)")
            return None
        print("    fullbody: generating with Flux Kontext (vibe transfer)...")
        from core.tools._image_clients import FluxKontextClient

        kontext = FluxKontextClient()
        vibe_prompt = (
            f"Transform this character into a completely different character: {prompt}. "
            "Keep the exact same anime art style, line weight, coloring technique, "
            "and background style. Full body, standing, white background."
        )
        fullbody_bytes = kontext.generate_from_reference(
            reference_image=vibe_reference,
            prompt=vibe_prompt,
            aspect_ratio="9:16",
        )
        fullbody_path.write_bytes(fullbody_bytes)
        size_kb = len(fullbody_bytes) / 1024
        print(f"    fullbody: saved ({size_kb:.0f} KB)")
    else:
        if style == "realistic" or not os.environ.get("NOVELAI_TOKEN"):
            if not os.environ.get("FAL_KEY"):
                print("    fullbody: SKIP (no FAL_KEY)")
                return None
            print("    fullbody: generating with Fal Flux Pro...")
            from core.tools._image_clients import FalTextToImageClient

            client = FalTextToImageClient()
            fullbody_bytes = client.generate_fullbody(prompt=prompt)
        else:
            print("    fullbody: generating with NovelAI...")
            from core.tools._image_clients import NovelAIClient

            client = NovelAIClient()
            fullbody_bytes = client.generate_fullbody(prompt=prompt)

        fullbody_path.write_bytes(fullbody_bytes)
        size_kb = len(fullbody_bytes) / 1024
        print(f"    fullbody: saved ({size_kb:.0f} KB)")

    # ── Step 2: Bust-up ──
    bustup_path = assets_dir / bustup_name
    if bustup_path.exists() and bustup_path.stat().st_size > 100:
        print("    bustup: exists, skipping")
    else:
        if not os.environ.get("FAL_KEY"):
            print("    bustup: SKIP (no FAL_KEY)")
        else:
            from core.tools._image_clients import (
                FluxKontextClient,
                _BUSTUP_PROMPT,
                _REALISTIC_BUSTUP_PROMPT,
            )

            print("    bustup: generating with Flux Kontext...")
            kontext = FluxKontextClient()
            bustup_prompt = _REALISTIC_BUSTUP_PROMPT if style == "realistic" else _BUSTUP_PROMPT
            bustup_bytes = kontext.generate_from_reference(
                reference_image=fullbody_bytes,
                prompt=bustup_prompt,
                aspect_ratio="3:4",
            )
            bustup_path.write_bytes(bustup_bytes)
            size_kb = len(bustup_bytes) / 1024
            print(f"    bustup: saved ({size_kb:.0f} KB)")

    # ── Step 3: Chibi ──
    chibi_path = assets_dir / chibi_name
    if chibi_path.exists() and chibi_path.stat().st_size > 100:
        print("    chibi: exists, skipping")
    else:
        if not os.environ.get("FAL_KEY"):
            print("    chibi: SKIP (no FAL_KEY)")
        else:
            from core.tools._image_clients import FluxKontextClient

            print("    chibi: generating with Flux Kontext...")
            kontext = FluxKontextClient()
            chibi_bytes = kontext.generate_from_reference(
                reference_image=fullbody_bytes,
                prompt=_CHIBI_PROMPT,
                aspect_ratio="1:1",
            )
            chibi_path.write_bytes(chibi_bytes)
            size_kb = len(chibi_bytes) / 1024
            print(f"    chibi: saved ({size_kb:.0f} KB)")

    return fullbody_bytes


# ── CLI ───────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate demo character assets using AnimaWorks image pipeline.",
    )
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="Generate assets for a specific preset only.",
    )
    parser.add_argument(
        "--character",
        help="Generate assets for a specific character only.",
    )
    args = parser.parse_args()

    api_keys = []
    if os.environ.get("NOVELAI_TOKEN"):
        api_keys.append("NOVELAI_TOKEN")
    if os.environ.get("FAL_KEY"):
        api_keys.append("FAL_KEY")

    if not api_keys:
        print("ERROR: No API keys found.")
        print("  Set NOVELAI_TOKEN for anime full-body generation")
        print("  Set FAL_KEY for Flux-based generation (bustup, chibi, realistic)")
        sys.exit(1)

    print(f"API keys available: {', '.join(api_keys)}")
    print()

    presets_to_run = {args.preset: PRESETS[args.preset]} if args.preset else PRESETS

    for preset_name, preset_info in presets_to_run.items():
        style = str(preset_info["style"])
        characters = list(preset_info["characters"])  # type: ignore[arg-type]
        supervisor = str(preset_info.get("supervisor", ""))

        if args.character:
            if args.character not in characters:
                continue
            characters = [args.character]

        print(f"=== {preset_name} (style={style}) ===")

        # For anime presets, generate supervisor first for vibe transfer
        vibe_ref: bytes | None = None
        if style == "anime" and supervisor and supervisor in characters:
            characters = [supervisor] + [c for c in characters if c != supervisor]

        for char_name in characters:
            is_supervisor = char_name == supervisor
            use_vibe = style == "anime" and not is_supervisor and vibe_ref is not None
            label = " (vibe transfer)" if use_vibe else " (anchor)" if is_supervisor and style == "anime" else ""
            print(f"  [{char_name}]{label}")
            try:
                fb = generate_character(
                    preset_name,
                    char_name,
                    style,
                    vibe_reference=vibe_ref if use_vibe else None,
                )
                if is_supervisor and fb is not None:
                    vibe_ref = fb
            except Exception as exc:
                print(f"  ERROR: {exc}")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
