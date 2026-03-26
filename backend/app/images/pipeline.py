from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import structlog
from PIL import Image

from app.models.blueprint import GameObjectBlueprint, VisualDescriptor

logger = structlog.get_logger()

RemoveBg: TypeAlias = Callable[[bytes], Awaitable[bytes]]

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# Sprite textures are saved at this resolution.  World size is determined
# separately by size_category on the client side.
TEXTURE_RESOLUTION = 512

# Fraction of the canvas the opaque content should fill (leaves a thin
# transparent border so collision shapes don't extend to the very edge).
FILL_FRACTION = 0.9


@dataclass
class SpriteResult:
    """Result of sprite generation."""

    sprite_url: str


def _prompt_hash(prompt: str) -> str:
    """Hash the image prompt for cache keying. Same prompt → same image."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def build_prompt(name: str, visual_descriptor: VisualDescriptor) -> str:
    """Build an image generation prompt from a name and VisualDescriptor."""
    parts = [
        "mixed media collage style paper cutout, side view, flat lighting, clean edges",
        f"{name}, {visual_descriptor.visual_description}",
        "single centered object, contrasting solid background color, no text",
    ]
    return ", ".join(parts)


def get_cached_sprite_path(prompt: str) -> Path:
    """Return the expected cache path for a given prompt."""
    h = _prompt_hash(prompt)
    return STATIC_DIR / "sprites" / f"{h}.png"



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
        logger.warning("crop_and_fit_empty_image")
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
    logger.debug("bg_removal_start", input_size=len(raw_bytes))
    output_bytes = await remove_bg(raw_bytes)
    logger.debug("bg_removal_complete", output_size=len(output_bytes))
    output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)

    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_sprite(
    blueprint: GameObjectBlueprint,
    remove_bg: RemoveBg,
) -> SpriteResult | None:
    """Full image pipeline: check cache → generate → remove bg → crop & fit → cache.

    Returns a SpriteResult with the URL, or None on failure.
    """
    from app.config import settings

    object_id = blueprint.id
    prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
    cache_path = get_cached_sprite_path(prompt)
    sprite_url = f"/static/sprites/{cache_path.name}"

    if settings.sprite_cache_enabled and cache_path.exists():
        logger.debug("sprite_cache_hit", object_id=object_id)
        return SpriteResult(sprite_url=sprite_url)

    logger.debug("sprite_cache_miss", object_id=object_id)
    t0 = time.monotonic()
    try:
        final_bytes = await _generate_static_sprite(prompt, remove_bg)

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(final_bytes)
        logger.debug(
            "sprite_cache_written",
            object_id=object_id,
            path=str(cache_path),
            size_bytes=len(final_bytes),
        )

        logger.info(
            "sprite_generated",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            size_bytes=len(final_bytes),
        )
        return SpriteResult(sprite_url=sprite_url)

    except (RuntimeError, TimeoutError, OSError, ValueError):
        logger.error(
            "sprite_generation_failed",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            exc_info=True,
        )
        return None
