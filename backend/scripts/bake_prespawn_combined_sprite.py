"""Bake a carry/ride combined sprite for a prespawn object.

Prespawns bypass the backend object-creation pipeline, so their carry/ride
combined sprite (the pre-rendered "player holding object" image that
``AffordanceSystem._get_combined_texture`` looks up) is never generated at
runtime. This script produces it offline from the already-baked base PNG and
writes it to ``godot/assets/prespawn/combined_{name}.png`` so
``PrespawnCatalog`` can preload it.

Name/description/affordance are sourced from ``godot/data/prespawns.json`` —
the single source of truth — so only the prespawn type_id is needed.

Usage:
    python backend/scripts/bake_prespawn_combined_sprite.py --name wooden_box
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.images.pipeline import generate_carry_ride_sprite  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRESPAWN_DIR = REPO_ROOT / "godot" / "assets" / "prespawn"
CATALOG_PATH = REPO_ROOT / "godot" / "data" / "prespawns.json"


async def bake(type_id: str) -> Path:
    catalog = json.loads(CATALOG_PATH.read_text())
    if type_id not in catalog:
        raise KeyError(f"'{type_id}' not found in {CATALOG_PATH}")
    entry = catalog[type_id]
    affordance = entry.get("affordance", 3)
    if affordance not in (0, 1):
        raise ValueError(
            f"'{type_id}' has affordance={affordance}; only CARRY (0) and MOUNT (1) "
            f"need a combined sprite."
        )

    base_path = PRESPAWN_DIR / f"{type_id}.png"
    if not base_path.exists():
        raise FileNotFoundError(
            f"Base prespawn sprite missing: {base_path}. "
            f"Run bake_prespawn_sprite.py first."
        )

    png_bytes = await generate_carry_ride_sprite(
        affordance,
        entry["name"],
        entry["visual_description"],
        base_path.read_bytes(),
    )
    out_path = PRESPAWN_DIR / f"combined_{type_id}.png"
    out_path.write_bytes(png_bytes)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--name",
        required=True,
        help="Prespawn type_id, matching the key in godot/data/prespawns.json "
        "and the base sprite filename (e.g. 'wooden_box').",
    )
    args = parser.parse_args()

    out_path = asyncio.run(bake(args.name))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
