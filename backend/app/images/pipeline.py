from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeAlias

import httpx
import structlog
from PIL import Image, ImageDraw

from app.models.blueprint import VisualDescriptor
from app.models.tags import SIZE_PIXEL_MAP, Tag

logger = structlog.get_logger()

RemoveBg: TypeAlias = Callable[[bytes], Awaitable[bytes]]

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# Tag-based placeholder colors
TAG_COLOR_MAP: dict[Tag, str] = {
    Tag.HEAT_SOURCE: "#FF4444",
    Tag.HOT: "#FF6600",
    Tag.MOLTEN: "#FF2200",
    Tag.FROZEN: "#88CCFF",
    Tag.COLD: "#44AAFF",
    Tag.LIVING: "#44CC44",
    Tag.TOXIC: "#88FF00",
    Tag.ELECTRIC: "#FFFF00",
    Tag.CORROSIVE: "#AAFF00",
    Tag.EXPLOSIVE: "#FF8800",
    Tag.GLOWING: "#FFFFAA",
    Tag.MAGNETIC: "#AA44FF",
    Tag.WIND_SOURCE: "#CCCCFF",
    Tag.LIQUID: "#4488FF",
    Tag.GAS: "#CCCCCC",
}


def _prompt_hash(prompt: str) -> str:
    """Hash the Flux prompt for cache keying. Same prompt → same image."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def generate_placeholder(visual_descriptor: VisualDescriptor, tags: list[Tag]) -> bytes:
    """Generate a colored rectangle placeholder PNG from the visual descriptor and tags."""
    size = SIZE_PIXEL_MAP[visual_descriptor.size_category]

    # Pick color: first matching tag color, or use primary color from descriptor
    color = visual_descriptor.color_primary
    for tag in tags:
        if tag in TAG_COLOR_MAP:
            color = TAG_COLOR_MAP[tag]
            break

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        [(2, 2), (size - 3, size - 3)],
        radius=4,
        fill=color,
        outline="#000000",
        width=1,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_prompt(visual_descriptor: VisualDescriptor) -> str:
    """Build a Flux image generation prompt from a VisualDescriptor."""
    vd = visual_descriptor
    parts = [
        "pixel art game sprite, side view, flat lighting, clean edges",
        f"{vd.size_category} {vd.base_form} made of {vd.material}",
        f"{vd.color_primary_name} with {vd.color_secondary_name} accents",
    ]
    if vd.visual_effects:
        parts.append(", ".join(vd.visual_effects))
    parts.append(f"single centered object, solid {vd.bg_color} background, no text")
    return ", ".join(parts)


def get_cached_sprite_path(prompt: str) -> Path:
    """Return the expected cache path for a given prompt."""
    h = _prompt_hash(prompt)
    return STATIC_DIR / "sprites" / f"{h}.png"


async def generate_sprite(
    object_id: str,
    visual_descriptor: VisualDescriptor,
    tags: list[Tag],
    remove_bg: RemoveBg,
) -> bytes | None:
    """Full image pipeline: check cache → generate → remove bg → resize → cache.

    Returns the final PNG bytes, or None on failure.
    """
    from app.config import settings
    from app.images.flux_client import generate_image

    prompt = build_prompt(visual_descriptor)
    cache_path = get_cached_sprite_path(prompt)

    if settings.sprite_cache_enabled and cache_path.exists():
        logger.debug("sprite_cache_hit", object_id=object_id)
        return cache_path.read_bytes()

    t0 = time.monotonic()
    try:
        raw_bytes = await generate_image(prompt)

        output_bytes = await remove_bg(raw_bytes)
        output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

        target_size = SIZE_PIXEL_MAP[visual_descriptor.size_category]
        output_img = output_img.resize((target_size, target_size), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        final_bytes = buf.getvalue()
        if settings.sprite_cache_enabled:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(final_bytes)

        logger.info(
            "sprite_generated",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            size_bytes=len(final_bytes),
        )
        return final_bytes

    except (httpx.HTTPError, TimeoutError, OSError, ValueError):
        logger.error(
            "sprite_generation_failed",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            exc_info=True,
        )
        return None
