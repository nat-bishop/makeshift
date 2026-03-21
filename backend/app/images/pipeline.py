from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw

from app.models.blueprint import VisualDescriptor
from app.models.tags import Tag

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

SIZE_MAP: dict[str, int] = {
    "tiny": 32,
    "small": 48,
    "medium": 64,
    "large": 96,
    "huge": 128,
}

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


def _descriptor_hash(vd: VisualDescriptor) -> str:
    """Stable hash of a VisualDescriptor for cache keying."""
    effects = ",".join(sorted(vd.visual_effects))
    data = (
        f"{vd.base_form}|{vd.material}|{vd.color_primary}"
        f"|{vd.color_secondary}|{effects}|{vd.size_category}"
    )
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def generate_placeholder(
    visual_descriptor: VisualDescriptor, tags: list[Tag]
) -> bytes:
    """Generate a colored rectangle placeholder PNG from the visual descriptor and tags."""
    size = SIZE_MAP.get(visual_descriptor.size_category, 64)

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
    effects_str = (
        ", ".join(visual_descriptor.visual_effects)
        if visual_descriptor.visual_effects
        else ""
    )
    parts = [
        "2D game sprite, side view",
        f"{visual_descriptor.size_category} {visual_descriptor.base_form}",
        f"made of {visual_descriptor.material}",
        f"{visual_descriptor.color_primary} with {visual_descriptor.color_secondary} accents",
    ]
    if effects_str:
        parts.append(effects_str)
    parts.append("pixel art, clean edges, white background, game asset, no text")
    return ", ".join(parts)


def get_cached_sprite_path(visual_descriptor: VisualDescriptor) -> Path:
    """Return the expected cache path for a given visual descriptor."""
    h = _descriptor_hash(visual_descriptor)
    return STATIC_DIR / "sprites" / f"{h}.png"


def get_placeholder_path(object_id: str) -> Path:
    """Return the placeholder path for an object."""
    return STATIC_DIR / "placeholders" / f"{object_id}.png"


async def generate_sprite(
    object_id: str,
    visual_descriptor: VisualDescriptor,
    tags: list[Tag],
    rembg_session: object,
) -> bytes | None:
    """Full image pipeline: check cache → generate → rembg → resize → cache.

    Returns the final PNG bytes, or None on failure.
    """
    from rembg import remove as rembg_remove

    from app.images.flux_client import generate_image

    # Check cache
    cache_path = get_cached_sprite_path(visual_descriptor)
    if cache_path.exists():
        return cache_path.read_bytes()

    try:
        # Generate via Flux
        prompt = build_prompt(visual_descriptor)
        raw_bytes = await generate_image(prompt)

        # Remove background with rembg
        output_bytes = rembg_remove(
            data=raw_bytes,
            session=rembg_session,
            alpha_matting=True,
        )
        output_img = Image.open(io.BytesIO(output_bytes)).convert("RGBA")

        # Resize to target size
        target_size = SIZE_MAP.get(visual_descriptor.size_category, 64)
        output_img = output_img.resize(
            (target_size, target_size), Image.Resampling.LANCZOS
        )

        # Save to cache
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        output_img.save(buf, format="PNG")
        final_bytes = buf.getvalue()
        cache_path.write_bytes(final_bytes)

        return final_bytes

    except Exception:
        return None


async def full_pipeline(
    object_id: str,
    visual_descriptor: VisualDescriptor,
    tags: list[Tag],
    rembg_session: object,
) -> tuple[bytes, bytes | None]:
    """Run the full image pipeline.

    Returns (placeholder_bytes, sprite_bytes_or_none).
    Placeholder is always generated synchronously.
    Sprite generation is attempted async and may fail.
    """
    # Always generate placeholder
    placeholder_bytes = generate_placeholder(visual_descriptor, tags)

    # Save placeholder to disk
    placeholder_path = get_placeholder_path(object_id)
    placeholder_path.parent.mkdir(parents=True, exist_ok=True)
    placeholder_path.write_bytes(placeholder_bytes)

    # Attempt sprite generation
    sprite_bytes = await generate_sprite(
        object_id, visual_descriptor, tags, rembg_session
    )

    return placeholder_bytes, sprite_bytes
