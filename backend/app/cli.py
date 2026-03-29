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
import sys
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


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

class Timer:
    """Accumulates named steps for a final summary."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, float, str]] = []  # (label, seconds, detail)
        self.t0 = time.monotonic()

    def add(self, label: str, seconds: float, detail: str = "") -> None:
        self.steps.append((label, seconds, detail))

    @property
    def total(self) -> float:
        return time.monotonic() - self.t0

    def print_summary(self) -> None:
        total = self.total
        w = max(len(s[0]) for s in self.steps) if self.steps else 0
        print("\n--- timing ---", file=sys.stderr)
        for label, secs, detail in self.steps:
            bar_len = int(40 * secs / total) if total > 0 else 0
            bar = "#" * bar_len
            pct = secs / total * 100 if total > 0 else 0
            line = f"  {label:<{w}}  {secs:6.2f}s  {pct:5.1f}%  {bar}"
            if detail:
                line += f"  {detail}"
            print(line, file=sys.stderr)
        print(f"  {'total':<{w}}  {total:6.2f}s", file=sys.stderr)


async def _run_llm(description: str, timer: Timer) -> Any:
    """Run the LLM creator agent with streaming. Adds steps to timer."""
    import uuid

    from app.creator.agent import _get_agent
    from app.models.behaviors import expand_behavior_spec
    from app.models.blueprint import GameObjectBlueprint

    agent = _get_agent()
    t0 = time.monotonic()
    ttft = None
    async with agent.run_stream(f"Create a game object for: {description}") as stream:
        async for _chunk, _is_last in stream.stream_responses(debounce_by=None):
            if ttft is None:
                ttft = time.monotonic() - t0
        spec = await stream.get_output()
    elapsed = time.monotonic() - t0

    usage = stream.usage()
    gen_time = elapsed - (ttft or 0)
    tok_s = round(usage.output_tokens / gen_time, 1) if gen_time > 0 else 0

    timer.add("llm prefill", ttft or 0, f"{usage.input_tokens} input tokens")
    timer.add(
        "llm generate",
        gen_time,
        f"{usage.output_tokens} output tokens, {tok_s} tok/s",
    )
    if usage.requests > 1:
        timer.add("llm retries", 0, f"{usage.requests} requests")

    behaviors = [expand_behavior_spec(b) for b in spec.behaviors]
    return GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=spec.name,
        description=description,
        tags=spec.tags,
        behaviors=behaviors,
        visual_descriptor=spec.visual_descriptor,
    )


async def _run_image(prompt: str, timer: Timer) -> bytes:
    """Run image generation. Adds step to timer."""
    from app.images.pipeline import get_generate_image

    generate_image = get_generate_image()
    t0 = time.monotonic()
    image_bytes = await generate_image(prompt)
    timer.add("image gen", time.monotonic() - t0, f"{len(image_bytes):,} bytes")
    return image_bytes


async def _run_bg_removal(raw_bytes: bytes, timer: Timer) -> bytes:
    """Run bg removal + crop. Adds step to timer."""
    import io

    from PIL import Image

    from app.images.pipeline import TEXTURE_RESOLUTION, _crop_and_fit, get_remove_bg

    remove_bg = get_remove_bg()
    t0 = time.monotonic()
    output_bytes = await remove_bg(raw_bytes)
    timer.add("bg removal", time.monotonic() - t0, f"{len(output_bytes):,} bytes")

    t0 = time.monotonic()
    output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)
    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    timer.add("crop & fit", time.monotonic() - t0)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


async def cmd_create(description: str) -> None:
    timer = Timer()
    blueprint = await _run_llm(description, timer)
    print(json.dumps(blueprint.model_dump(mode="json"), indent=2))
    timer.print_summary()


async def cmd_image(prompt: str, out_path: Path) -> None:
    from app.config import settings

    timer = Timer()
    image_bytes = await _run_image(prompt, timer)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)
    print(
        json.dumps(
            {
                "path": str(out_path),
                "size_bytes": len(image_bytes),
                "backend": settings.image_backend,
            },
            indent=2,
        )
    )
    timer.print_summary()


async def cmd_sprite(description: str, out_path: str | None, skip_llm: bool) -> None:
    from app.config import settings
    from app.images.pipeline import build_prompt
    from app.models.blueprint import VisualDescriptor

    timer = Timer()

    if skip_llm:
        name = description
        visual = VisualDescriptor(visual_description=description, size_category="medium")
        prompt = build_prompt(name, visual)
    else:
        blueprint = await _run_llm(description, timer)
        prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
        name = blueprint.name

    raw_bytes = await _run_image(prompt, timer)
    sprite_bytes = await _run_bg_removal(raw_bytes, timer)

    if out_path is None:
        safe_name = name.lower().replace(" ", "_")
        out_path = f"{safe_name}.png"
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(sprite_bytes)

    result: dict = {
        "path": out_path,
        "size_bytes": len(sprite_bytes),
        "prompt": prompt,
        "backend": settings.image_backend,
        "bg_removal": settings.bg_removal_backend,
    }
    print(json.dumps(result, indent=2))
    timer.print_summary()


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
            checks["services"]["birefnet"] = "in-process (GPU)"
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
