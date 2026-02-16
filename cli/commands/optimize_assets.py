from __future__ import annotations

import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register(subparsers: argparse._SubParsersAction) -> None:
    """Register the optimize-assets subcommand."""
    parser = subparsers.add_parser(
        "optimize-assets",
        help="Optimize existing 3D assets (strip meshes from animations, compress models)",
    )
    parser.add_argument(
        "--anima", "-p",
        help="Optimize assets for a specific anima only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> None:
    from core.paths import get_animas_dir
    from core.tools.image_gen import optimize_glb, strip_mesh_from_glb

    animas_dir = get_animas_dir()
    if not animas_dir.exists():
        print(f"Animas directory not found: {animas_dir}")
        return

    if args.anima:
        anima_dirs = [animas_dir / args.anima]
    else:
        anima_dirs = sorted(
            d for d in animas_dir.iterdir()
            if d.is_dir() and (d / "assets").is_dir()
        )

    total_before = 0
    total_after = 0

    for anima_dir in anima_dirs:
        assets_dir = anima_dir / "assets"
        if not assets_dir.exists():
            continue

        name = anima_dir.name
        print(f"\n=== {name} ===")

        # Strip meshes from animation GLBs
        for anim_file in sorted(assets_dir.glob("anim_*.glb")):
            size_before = anim_file.stat().st_size
            total_before += size_before
            if args.dry_run:
                print(f"  [DRY-RUN] Would strip mesh from {anim_file.name} ({size_before:,} bytes)")
                total_after += size_before
            else:
                strip_mesh_from_glb(anim_file)
                size_after = anim_file.stat().st_size
                total_after += size_after
                print(f"  Stripped {anim_file.name}: {size_before:,} → {size_after:,} bytes")

        # Compress model GLBs with Draco
        for model_file in sorted(assets_dir.glob("avatar_chibi*.glb")):
            size_before = model_file.stat().st_size
            total_before += size_before
            if args.dry_run:
                print(f"  [DRY-RUN] Would compress {model_file.name} ({size_before:,} bytes)")
                total_after += size_before
            else:
                optimize_glb(model_file)
                size_after = model_file.stat().st_size
                total_after += size_after
                print(f"  Compressed {model_file.name}: {size_before:,} → {size_after:,} bytes")

    print(f"\nTotal: {total_before:,} → {total_after:,} bytes")
    if total_before > 0:
        reduction = (1 - total_after / total_before) * 100
        print(f"Reduction: {reduction:.1f}%")
