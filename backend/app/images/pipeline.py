from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
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

# Sprite textures are saved at this resolution.  World size is determined
# separately by size_category on the client side.
TEXTURE_RESOLUTION = 512

# Fraction of the canvas the opaque content should fill (leaves a thin
# transparent border so collision shapes don't extend to the very edge).
FILL_FRACTION = 0.9

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


@dataclass
class SpriteResult:
    """Result of sprite generation."""

    sprite_url: str


def _prompt_hash(prompt: str) -> str:
    """Hash the image prompt for cache keying. Same prompt → same image."""
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
        "mixed media collage style paper cutout, side view, flat lighting, clean edges",
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


def get_sprite_url(prompt: str) -> str:
    """Public URL path for a sprite's cache file."""
    return f"/static/sprites/{get_cached_sprite_path(prompt).name}"


def _crop_and_fit(
    img: Image.Image,
    target_size: int,
    fill_fraction: float = FILL_FRACTION,
) -> Image.Image:
    """Crop to opaque content and fit within *target_size*, preserving aspect ratio.

    The opaque region is scaled to fill *fill_fraction* of the canvas
    (default 90 %) and centred on a transparent square canvas.
    """
    bbox = img.getbbox()
    if bbox is None:
        return Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))

    cropped = img.crop(bbox)
    max_extent = int(target_size * fill_fraction)
    w, h = cropped.size
    scale = min(max_extent / w, max_extent / h)
    new_w = max(1, round(w * scale))
    new_h = max(1, round(h * scale))
    resized = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
    paste_x = (target_size - new_w) // 2
    paste_y = (target_size - new_h) // 2
    canvas.paste(resized, (paste_x, paste_y))
    return canvas


async def _generate_static_sprite(
    prompt: str,
    remove_bg: RemoveBg,
) -> bytes:
    """Generate a single static sprite via Gemini at 512x512."""
    from app.images.gemini_client import generate_image

    raw_bytes = await generate_image(prompt)
    output_bytes = await remove_bg(raw_bytes)
    output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)

    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_sprite(
    object_id: str,
    visual_descriptor: VisualDescriptor,
    remove_bg: RemoveBg,
) -> SpriteResult | None:
    """Full image pipeline: check cache → generate → remove bg → crop & fit → cache.

    Returns a SpriteResult with the URL, or None on failure.
    """
    from app.config import settings

    prompt = build_prompt(visual_descriptor)
    cache_path = get_cached_sprite_path(prompt)
    sprite_url = get_sprite_url(prompt)

    if settings.sprite_cache_enabled and cache_path.exists():
        logger.debug("sprite_cache_hit", object_id=object_id)
        return SpriteResult(sprite_url=sprite_url)

    t0 = time.monotonic()
    try:
        final_bytes = await _generate_static_sprite(prompt, remove_bg)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(final_bytes)

        logger.info(
            "sprite_generated",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            size_bytes=len(final_bytes),
        )
        return SpriteResult(sprite_url=sprite_url)

    except (httpx.HTTPError, TimeoutError, OSError, ValueError):
        logger.error(
            "sprite_generation_failed",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            exc_info=True,
        )
        return None
