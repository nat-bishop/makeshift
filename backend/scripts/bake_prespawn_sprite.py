"""Bake a prespawn sprite PNG for level-defined game objects.

Prespawn objects (e.g. the wooden crate in level 1) are placed directly by
level code instead of being generated from a description at runtime. They need
a baked PNG committed under ``godot/assets/prespawn/`` so the Godot client can
load them synchronously on level load.

This script reuses the exact image pipeline the live creator uses
(``generate_static_sprite`` from ``app.images.pipeline``) so prespawn art
matches the style of runtime-generated objects.

Usage:
    python backend/scripts/bake_prespawn_sprite.py \\
        --name wooden_crate \\
        --display-name "wooden crate" \\
        --description "a small wooden shipping crate with planks and nails"
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.images.pipeline import generate_static_sprite  # noqa: E402
from app.prompts.image import build_text_to_image_prompt  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "godot" / "assets" / "prespawn"


async def bake(file_name: str, display_name: str, visual_description: str) -> Path:
    prompt = build_text_to_image_prompt(display_name, visual_description)
    png_bytes = await generate_static_sprite(prompt)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{file_name}.png"
    out_path.write_bytes(png_bytes)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        required=True,
        help="Output filename stem, e.g. 'wooden_crate' -> wooden_crate.png",
    )
    parser.add_argument(
        "--display-name",
        required=True,
        help="Human-readable name used in the prompt, e.g. 'wooden crate'",
    )
    parser.add_argument(
        "--description",
        required=True,
        help="Visual description passed to FLUX, e.g. "
        "'a small wooden shipping crate with planks and nails'",
    )
    args = parser.parse_args()

    out_path = asyncio.run(bake(args.name, args.display_name, args.description))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
