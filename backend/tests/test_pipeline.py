"""Tests for image pipeline pure functions."""

from __future__ import annotations

import io
import re

from PIL import Image

from app.images.pipeline import (
    STATIC_DIR,
    TAG_COLOR_MAP,
    _descriptor_hash,
    build_prompt,
    generate_placeholder,
    get_cached_sprite_path,
)
from app.models.blueprint import VisualDescriptor
from app.models.tags import SIZE_PIXEL_MAP, Tag


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
    return VisualDescriptor(**defaults)


def test_descriptor_hash_deterministic() -> None:
    vd = _make_visual()
    assert _descriptor_hash(vd) == _descriptor_hash(vd)


def test_descriptor_hash_different_inputs() -> None:
    a = _make_visual(base_form="cube")
    b = _make_visual(base_form="sphere")
    assert _descriptor_hash(a) != _descriptor_hash(b)


def test_descriptor_hash_length() -> None:
    h = _descriptor_hash(_make_visual())
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
    r, g, b, _a = img.getpixel((cx, cy))
    expected = TAG_COLOR_MAP[Tag.HEAT_SOURCE]
    er, eg, eb = int(expected[1:3], 16), int(expected[3:5], 16), int(expected[5:7], 16)
    assert (r, g, b) == (er, eg, eb)


def test_generate_placeholder_no_matching_tag() -> None:
    vd = _make_visual(color_primary="#123456")
    data = generate_placeholder(vd, [Tag.SOLID])
    img = Image.open(io.BytesIO(data)).convert("RGBA")
    cx, cy = img.size[0] // 2, img.size[1] // 2
    r, g, b, _a = img.getpixel((cx, cy))
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
    path = get_cached_sprite_path(_make_visual())
    assert path.suffix == ".png"
    assert path.parent == STATIC_DIR / "sprites"


def test_get_cached_sprite_path_deterministic() -> None:
    vd = _make_visual()
    assert get_cached_sprite_path(vd) == get_cached_sprite_path(vd)
