"""Tests for image pipeline pure functions."""

from __future__ import annotations

import io
import re

from app.images.pipeline import (
    STATIC_DIR,
    TAG_COLOR_MAP,
    _crop_and_fit,
    _prompt_hash,
    build_prompt,
    generate_placeholder,
    get_cached_sprite_path,
)
from app.models.blueprint import VisualDescriptor
from app.models.tags import SIZE_PIXEL_MAP, Tag
from PIL import Image


def _make_visual(**kwargs: object) -> VisualDescriptor:
    defaults: dict[str, object] = {
        "base_form": "cube",
        "material": "stone",
        "color_primary": "#888888",
        "color_primary_name": "gray",
        "color_secondary": "#666666",
        "color_secondary_name": "dark gray",
        "visual_effects": [],
        "size_category": "medium",
        "bg_color": "#4A6741",
    }
    defaults.update(kwargs)
    return VisualDescriptor(**defaults)  # type: ignore[arg-type]


def test_prompt_hash_deterministic() -> None:
    prompt = build_prompt(_make_visual())
    assert _prompt_hash(prompt) == _prompt_hash(prompt)


def test_prompt_hash_different_inputs() -> None:
    a = build_prompt(_make_visual(base_form="cube"))
    b = build_prompt(_make_visual(base_form="sphere"))
    assert _prompt_hash(a) != _prompt_hash(b)


def test_prompt_hash_length() -> None:
    h = _prompt_hash(build_prompt(_make_visual()))
    assert len(h) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", h)


def test_generate_placeholder_returns_png() -> None:
    data = generate_placeholder(_make_visual(), [])
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_generate_placeholder_tag_color() -> None:
    vd = _make_visual()
    data = generate_placeholder(vd, [Tag.HEAT_SOURCE])
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    cx, cy = img.size[0] // 2, img.size[1] // 2
    r, g, b, _a = img.getpixel((cx, cy))  # type: ignore[misc]
    expected = TAG_COLOR_MAP[Tag.HEAT_SOURCE]
    er, eg, eb = int(expected[1:3], 16), int(expected[3:5], 16), int(expected[5:7], 16)
    assert (r, g, b) == (er, eg, eb)


def test_generate_placeholder_no_matching_tag() -> None:
    vd = _make_visual(color_primary="#123456")
    data = generate_placeholder(vd, [Tag.SOLID])
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    cx, cy = img.size[0] // 2, img.size[1] // 2
    r, g, b, _a = img.getpixel((cx, cy))  # type: ignore[misc]
    assert (r, g, b) == (0x12, 0x34, 0x56)


def test_generate_placeholder_size() -> None:
    for size_cat, pixels in SIZE_PIXEL_MAP.items():
        vd = _make_visual(size_category=size_cat)
        data = generate_placeholder(vd, [])
        img = Image.open(io.BytesIO(data))
        assert img.size == (pixels, pixels), f"Failed for {size_cat}"


def test_build_prompt_content() -> None:
    vd = _make_visual(
        base_form="sword",
        material="iron",
        color_primary_name="silver",
        color_secondary_name="black",
        size_category="large",
    )
    prompt = build_prompt(vd)
    for word in ("sword", "iron", "silver", "black", "large"):
        assert word in prompt


def test_build_prompt_with_effects() -> None:
    vd = _make_visual(visual_effects=["glowing", "flaming"])
    prompt = build_prompt(vd)
    assert "glowing" in prompt
    assert "flaming" in prompt


def test_build_prompt_without_effects() -> None:
    vd = _make_visual(visual_effects=[])
    prompt = build_prompt(vd)
    # No double commas or empty sections
    assert ",," not in prompt
    assert ", ," not in prompt


def test_get_cached_sprite_path() -> None:
    prompt = build_prompt(_make_visual())
    path = get_cached_sprite_path(prompt)
    assert path.suffix == ".png"
    assert path.parent == STATIC_DIR / "sprites"


def test_get_cached_sprite_path_deterministic() -> None:
    prompt = build_prompt(_make_visual())
    assert get_cached_sprite_path(prompt) == get_cached_sprite_path(prompt)


# --- _crop_and_fit tests ---


def test_crop_and_fit_basic() -> None:
    """Opaque region in center of larger image fills ~90% of target canvas."""
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    # Draw a 60x60 opaque block in the center
    for x in range(70, 130):
        for y in range(70, 130):
            img.putpixel((x, y), (255, 0, 0, 255))

    result = _crop_and_fit(img, 100)
    assert result.size == (100, 100)
    # The 60x60 block should be scaled to ~90px (90% of 100) and centered
    bbox = result.getbbox()
    assert bbox is not None
    content_w = bbox[2] - bbox[0]
    content_h = bbox[3] - bbox[1]
    assert content_w == content_h  # Square content stays square
    assert 85 <= content_w <= 95  # ~90% of 100


def test_crop_and_fit_fully_transparent() -> None:
    """Fully transparent image returns empty canvas at target size."""
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    result = _crop_and_fit(img, 64)
    assert result.size == (64, 64)
    assert result.getbbox() is None


def test_crop_and_fit_preserves_aspect_ratio() -> None:
    """Tall narrow content stays tall and narrow, centered horizontally."""
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    # Draw a 20x100 tall bar
    for x in range(90, 110):
        for y in range(50, 150):
            img.putpixel((x, y), (0, 255, 0, 255))

    result = _crop_and_fit(img, 100)
    assert result.size == (100, 100)
    bbox = result.getbbox()
    assert bbox is not None
    content_w = bbox[2] - bbox[0]
    content_h = bbox[3] - bbox[1]
    # Height should be ~90 (fills 90%), width should be ~18 (preserves 1:5 ratio)
    assert content_h > content_w * 3  # Still tall and narrow
    assert 85 <= content_h <= 95


def test_crop_and_fit_content_fills_canvas() -> None:
    """Content already filling entire image resizes to target."""
    img = Image.new("RGBA", (500, 500), (255, 0, 0, 255))  # Fully opaque
    result = _crop_and_fit(img, 128)
    assert result.size == (128, 128)
    bbox = result.getbbox()
    assert bbox is not None
    content_w = bbox[2] - bbox[0]
    assert 110 <= content_w <= 120  # ~90% of 128
