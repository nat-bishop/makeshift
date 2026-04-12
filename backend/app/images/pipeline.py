from __future__ import annotations

import asyncio
import hashlib
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image

from app.images.local_image import generate_image, generate_image_edit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.models.blueprint import GameObjectBlueprint

logger = structlog.get_logger()


# Background removal: lazy singleton so module import doesn't trigger CUDA /
# model weight loading (expensive + not test-environment friendly).
_remove_bg_impl: Callable[[bytes], Awaitable[bytes]] | None = None


async def remove_bg(image_bytes: bytes) -> bytes:
    """Remove the background from an image via in-process BiRefNet."""
    global _remove_bg_impl
    if _remove_bg_impl is None:
        from app.images.birefnet_bg import make_birefnet_remover

        _remove_bg_impl = make_birefnet_remover()
    return await _remove_bg_impl(image_bytes)


STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# Sprite textures are saved at this resolution.  World size is determined
# separately by size_category on the client side.
TEXTURE_RESOLUTION = 512

# Fraction of the canvas the opaque content should fill (leaves a thin
# transparent border so collision shapes don't extend to the very edge).
FILL_FRACTION = 0.9

# Reference images for img2img are 256x256 on white background -- experimentally
# this gives the fewest artifacts and best likeness (see docs/image-combination.md).
REFERENCE_SIZE = 256


# ── img2img prompt templates (art style wrapping, never LLM-generated) ──
IMG2IMG_STYLE = "mixed media collage style paper cutout, side view, flat lighting, clean edges"
IMG2IMG_SUFFIX_OBJECT = "single centered object, contrasting solid background color, no text"
IMG2IMG_SUFFIX_SCENE = "single centered scene, contrasting solid background color, no text"

# Headroom for LLM overshooting the ~20-25 word cap in the instructions.
_IMG2IMG_MAX_TOKENS = 250


# ── LLM instructions for each img2img use case ──
_CARRY_LLM_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is carrying an object. You receive descriptions of both. "
    "Write a visual description of the character holding/carrying the object "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

_RIDE_LLM_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is riding a mount. You receive descriptions of both. "
    "Write a visual description of the character sitting on/riding the mount "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

_DESTRUCTION_LLM_INSTRUCTION = (
    "You write visual descriptions for a mixed media collage paper cutout game. "
    "An object was smashed. Describe the debris as a single paper cutout sprite. "
    "The debris must look completely different from the original object's silhouette. "
    "It should be a low, flat pile or scatter of broken fragments. "
    "Reference the original's specific colors and material textures. "
    "Under 20 words. Output ONLY the visual description."
)

_COMBINE_LLM_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "Two objects are being combined. Choose the best approach:\n"
    "- MATERIAL: 'the shape of B but made from/constructed of A' "
    "(when A is a material-like thing)\n"
    "- THEMED: 'B with A elements, accents, and motifs woven into its design' "
    "(when A is an aesthetic)\n"
    "- SEMANTIC: 'an A B, combining elements of both into one object' "
    "(when both contribute equally)\n"
    "Pick the best fit. Reference specific visual details from both source descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

_COMBINE_ORDER_INSTRUCTION = (
    "Two objects are being combined into one sprite image. "
    "The first reference image has more influence on the overall shape and form. "
    "Pick which object should be the primary shape reference."
)


@dataclass
class SpriteResult:
    """Result of sprite generation."""

    sprite_url: str
    sprite_bytes: bytes


def _prompt_hash(prompt: str) -> str:
    """Hash the image prompt for cache keying. Same prompt → same image."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def build_prompt(name: str, visual_description: str) -> str:
    """Build a narrative image prompt from a name and visual description."""
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{visual_description} "
        f"Side view, single centered object on a solid contrasting background. "
        f"Flat lighting, clean edges, no text."
    )


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


def _postprocess_sprite(raw_bytes: bytes) -> bytes:
    """Common tail for image generation: bg removal has already run -> crop, save."""
    output_img = Image.open(io.BytesIO(raw_bytes)).convert("RGBA")
    output_img = _crop_and_fit(output_img, TEXTURE_RESOLUTION)
    buf = io.BytesIO()
    output_img.save(buf, format="PNG")
    return buf.getvalue()


async def generate_static_sprite(prompt: str) -> bytes:
    """Generate a single static sprite at 512x512 via text-to-image."""
    raw_bytes = await generate_image(prompt)
    logger.debug("bg_removal_start", input_size=len(raw_bytes))
    output_bytes = await remove_bg(raw_bytes)
    logger.debug("bg_removal_complete", output_size=len(output_bytes))
    return _postprocess_sprite(output_bytes)


# ── img2img reference image helpers ──


def prepare_reference(sprite_bytes: bytes) -> bytes:
    """Convert a 512x512 RGBA sprite to a 256x256 white-bg reference for img2img."""
    img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
    img = img.resize((REFERENCE_SIZE, REFERENCE_SIZE), Image.Resampling.LANCZOS)
    bg = Image.new("RGBA", (REFERENCE_SIZE, REFERENCE_SIZE), (255, 255, 255, 255))
    bg.paste(img, (0, 0), img)
    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


_PLAYER_SHEET_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "godot"
    / "assets"
    / "sprites"
    / "player"
    / "player_sheet.png"
)

_player_sprite_cache: bytes | None = None


def get_player_sprite() -> bytes:
    """Extract the player's first idle frame from the sprite sheet (cached).

    The player sheet is a 5x5 grid; the first frame (top-left) is the idle pose.
    Output: 512x512 RGBA PNG centered on a transparent canvas.
    """
    global _player_sprite_cache
    if _player_sprite_cache is not None:
        return _player_sprite_cache
    sheet = Image.open(_PLAYER_SHEET_PATH).convert("RGBA")
    frame_w = sheet.width // 5
    frame_h = sheet.height // 5
    frame = sheet.crop((0, 0, frame_w, frame_h))
    canvas = _crop_and_fit(frame, TEXTURE_RESOLUTION)
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    _player_sprite_cache = buf.getvalue()
    logger.info("player_sprite_extracted", size_bytes=len(_player_sprite_cache))
    return _player_sprite_cache


async def generate_edited_sprite(
    prompt: str,
    reference_images: list[tuple[str, bytes]],
) -> bytes:
    """Run the FLUX Kontext img2img pipeline: edits -> bg removal -> crop 512x512.

    Args:
        prompt: Full assembled prompt (style + description + suffix).
        reference_images: Already-prepared 256x256 white-bg PNGs as (filename, bytes).
    """
    raw_bytes = await generate_image_edit(prompt, reference_images)
    logger.debug("edit_bg_removal_start", input_size=len(raw_bytes))
    output_bytes = await remove_bg(raw_bytes)
    logger.debug("edit_bg_removal_complete", output_size=len(output_bytes))
    return _postprocess_sprite(output_bytes)


# ── Use case 1: Carry/Ride combined sprite ──


async def generate_carry_ride_sprite(
    affordance: int,
    object_name: str,
    object_visual: str,
    object_sprite_bytes: bytes,
) -> bytes:
    """Generate a carry/ride combined sprite via img2img.

    Character is always img1 (T10), object is always img2 (T20).
    """
    from app.creator.llm import ask_text

    if affordance == 1:
        instruction = _RIDE_LLM_INSTRUCTION
        action = "riding"
        role = "Mount"
    else:
        instruction = _CARRY_LLM_INSTRUCTION
        action = "carrying"
        role = "Object"

    user_prompt = (
        f"Character: player\n"
        f"{role}: {object_name} — {object_visual}\n"
        f"Describe the player {action} the {role.lower()}:"
    )
    llm_desc = await ask_text(
        user_prompt,
        max_tokens=_IMG2IMG_MAX_TOKENS,
        instructions=instruction,
    )
    full_prompt = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_SCENE}"

    char_ref = prepare_reference(get_player_sprite())
    obj_ref = prepare_reference(object_sprite_bytes)

    logger.info(
        "carry_ride_img2img_start",
        affordance=affordance,
        object_name=object_name,
        llm_desc=llm_desc,
    )
    return await generate_edited_sprite(
        full_prompt,
        [("character.png", char_ref), ("object.png", obj_ref)],
    )


# ── Use case 2: Destruction debris sprite ──


async def generate_destruction_sprite(
    object_name: str,
    object_visual: str,
    destruction_result_name: str,
    object_sprite_bytes: bytes,
) -> bytes:
    """Generate a destruction debris sprite via single-reference img2img.

    The original sprite provides color/material continuity; the LLM description
    provides a shape that is visually distinct from the original silhouette.
    """
    from app.creator.llm import ask_text

    user_prompt = (
        f"Object: {object_name} — {object_visual}\n"
        f"Debris name: {destruction_result_name}\n"
        f"Describe the destroyed remains:"
    )
    llm_desc = await ask_text(
        user_prompt,
        max_tokens=_IMG2IMG_MAX_TOKENS,
        instructions=_DESTRUCTION_LLM_INSTRUCTION,
    )
    full_prompt = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_OBJECT}"

    obj_ref = prepare_reference(object_sprite_bytes)

    logger.info(
        "destruction_img2img_start",
        object_name=object_name,
        debris=destruction_result_name,
        llm_desc=llm_desc,
    )
    return await generate_edited_sprite(
        full_prompt,
        [("object.png", obj_ref)],
    )


# ── Use case 3: Object combination hybrid sprite ──


async def generate_combination_sprite(
    name_a: str,
    visual_a: str,
    sprite_a: bytes,
    name_b: str,
    visual_b: str,
    sprite_b: bytes,
) -> bytes:
    """Generate a hybrid object sprite from two source objects via img2img.

    Two parallel LLM calls: one picks image order, one generates the description.
    The LLM is taught the material / themed / semantic combination patterns and
    picks the best fit per pair.
    """
    from app.creator.llm import ask_choice, ask_text

    order_prompt = f"1: {name_a}\n2: {name_b}"
    desc_prompt = (
        f"Object A: {name_a} — {visual_a}\n"
        f"Object B: {name_b} — {visual_b}\n"
        f"Write the visual description for combining A with B:"
    )

    order_str, llm_desc = await asyncio.gather(
        ask_choice(
            order_prompt,
            choices=("1", "2"),
            default="1",
            instructions=_COMBINE_ORDER_INSTRUCTION,
        ),
        ask_text(
            desc_prompt,
            max_tokens=_IMG2IMG_MAX_TOKENS,
            instructions=_COMBINE_LLM_INSTRUCTION,
        ),
    )

    full_prompt = f"{IMG2IMG_STYLE}, {llm_desc}, {IMG2IMG_SUFFIX_OBJECT}"

    ref_a = prepare_reference(sprite_a)
    ref_b = prepare_reference(sprite_b)

    if order_str == "1":
        images = [(f"{name_a}.png", ref_a), (f"{name_b}.png", ref_b)]
    else:
        images = [(f"{name_b}.png", ref_b), (f"{name_a}.png", ref_a)]

    logger.info(
        "combine_img2img_start",
        name_a=name_a,
        name_b=name_b,
        order=order_str,
        llm_desc=llm_desc,
    )
    return await generate_edited_sprite(full_prompt, images)


# ── Object creation pipeline entry point ──


async def generate_sprite(
    blueprint: GameObjectBlueprint,
) -> SpriteResult | None:
    """Full image pipeline: check cache → generate → remove bg → crop & fit → cache.

    Returns a SpriteResult with the URL, or None on failure.
    """
    from app.config import settings

    object_id = blueprint.id
    prompt = build_prompt(blueprint.name, blueprint.visual_description)
    cache_path = get_cached_sprite_path(prompt)
    sprite_url = f"/static/sprites/{cache_path.name}"

    if settings.sprite_cache_enabled and cache_path.exists():
        logger.debug("sprite_cache_hit", object_id=object_id)
        return SpriteResult(sprite_url=sprite_url, sprite_bytes=cache_path.read_bytes())

    logger.debug("sprite_cache_miss", object_id=object_id)
    t0 = time.monotonic()
    try:
        final_bytes = await generate_static_sprite(prompt)

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
        return SpriteResult(sprite_url=sprite_url, sprite_bytes=final_bytes)

    except (RuntimeError, TimeoutError, OSError, ValueError):
        logger.error(
            "sprite_generation_failed",
            object_id=object_id,
            elapsed=round(time.monotonic() - t0, 2),
            exc_info=True,
        )
        return None
