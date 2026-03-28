"""Makeshift CLI — test image generation, LLM creator, and sprite pipeline standalone.

Usage:
    uv run python -m app.cli create "fire sword"
    uv run python -m app.cli image "a pixel art sword" --out sword.png
    uv run python -m app.cli sprite "fire sword" --out fire_sword.png
    uv run python -m app.cli status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(prog="makeshift", description="Makeshift CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Run LLM creator agent")
    p_create.add_argument("description", help="Object description")

    p_image = sub.add_parser("image", help="Generate a raw image (no bg removal)")
    p_image.add_argument("prompt", help="Image generation prompt")
    p_image.add_argument("--out", "-o", default="output.png", help="Output file path")

    p_sprite = sub.add_parser("sprite", help="Full sprite pipeline (LLM + image + bg removal)")
    p_sprite.add_argument("description", help="Object description")
    p_sprite.add_argument("--out", "-o", default=None, help="Output PNG path (default: <name>.png)")
    p_sprite.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM, use description as raw visual prompt",
    )

    sub.add_parser("status", help="Check health of configured services")

    args = parser.parse_args()
    asyncio.run(_dispatch(args))


async def _dispatch(args: argparse.Namespace) -> None:
    from app.logging_setup import setup_logging

    setup_logging()

    if args.command == "create":
        await cmd_create(args.description)
    elif args.command == "image":
        await cmd_image(args.prompt, Path(args.out))
    elif args.command == "sprite":
        await cmd_sprite(args.description, args.out, args.skip_llm)
    elif args.command == "status":
        await cmd_status()


async def cmd_create(description: str) -> None:
    from app.creator.agent import create_object

    t0 = time.monotonic()
    blueprint = await create_object(description)
    elapsed = time.monotonic() - t0

    output = blueprint.model_dump(mode="json")
    output["_meta"] = {"elapsed_seconds": round(elapsed, 2)}
    print(json.dumps(output, indent=2))


async def cmd_image(prompt: str, out_path: Path) -> None:
    from app.config import settings
    from app.images.pipeline import get_generate_image

    generate_image = get_generate_image()

    t0 = time.monotonic()
    image_bytes = await generate_image(prompt)
    elapsed = time.monotonic() - t0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)
    print(
        json.dumps(
            {
                "path": str(out_path),
                "size_bytes": len(image_bytes),
                "elapsed_seconds": round(elapsed, 2),
                "backend": settings.image_backend,
            },
            indent=2,
        )
    )


async def cmd_sprite(description: str, out_path: str | None, skip_llm: bool) -> None:
    from app.config import settings
    from app.images.pipeline import build_prompt, generate_static_sprite
    from app.models.blueprint import VisualDescriptor

    blueprint_json = None
    if skip_llm:
        name = description
        visual = VisualDescriptor(visual_description=description, size_category="medium")
        prompt = build_prompt(name, visual)
    else:
        from app.creator.agent import create_object

        blueprint = await create_object(description)
        blueprint_json = blueprint.model_dump(mode="json")
        prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
        name = blueprint.name

    t0 = time.monotonic()
    sprite_bytes = await generate_static_sprite(prompt)
    elapsed = time.monotonic() - t0

    if out_path is None:
        safe_name = name.lower().replace(" ", "_")
        out_path = f"{safe_name}.png"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(sprite_bytes)

    result: dict = {
        "path": out_path,
        "size_bytes": len(sprite_bytes),
        "elapsed_seconds": round(elapsed, 2),
        "prompt": prompt,
        "backend": settings.image_backend,
        "bg_removal": settings.bg_removal_backend,
    }
    if blueprint_json:
        result["blueprint"] = blueprint_json
    print(json.dumps(result, indent=2))


async def cmd_status() -> None:
    import httpx

    from app.config import settings

    checks: dict = {
        "config": {
            "image_backend": settings.image_backend,
            "bg_removal_backend": settings.bg_removal_backend,
            "llm_model": settings.llm_model,
            "local_llm_url": settings.local_llm_url,
            "sprite_cache_enabled": settings.sprite_cache_enabled,
        },
        "services": {},
    }

    async with httpx.AsyncClient(timeout=3) as client:
        if settings.image_backend == "local":
            checks["services"]["local_flux"] = await _check_health(
                client, f"{settings.local_image_url}/health"
            )
        if settings.bg_removal_backend == "local":
            checks["services"]["local_rembg"] = await _check_health(
                client, f"{settings.bg_removal_url}/health"
            )
        if settings.local_llm_url:
            base = settings.local_llm_url.rstrip("/").removesuffix("/v1")
            checks["services"]["local_llm"] = await _check_health(
                client, f"{base}/health"
            )

    checks["services"]["google_api_key"] = "set" if settings.google_api_key else "missing"
    checks["services"]["fal_key"] = "set" if settings.fal_key else "missing"

    print(json.dumps(checks, indent=2))


async def _check_health(client: Any, url: str) -> str:
    try:
        r = await client.get(url)
        return "ok" if r.status_code == 200 else f"error ({r.status_code})"
    except Exception as e:
        return f"unreachable ({e.__class__.__name__})"


if __name__ == "__main__":
    main()
