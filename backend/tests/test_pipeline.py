"""Tests for image pipeline pure functions."""

from __future__ import annotations

import re

from app.images.pipeline import (
    STATIC_DIR,
    _crop_and_fit,
    _prompt_hash,
    get_cached_sprite_path,
)
from app.prompts.image import build_text_to_image_prompt
from PIL import Image


def test_prompt_hash_deterministic() -> None:
    prompt = build_text_to_image_prompt("Cube", "a gray stone cube")
    assert _prompt_hash(prompt) == _prompt_hash(prompt)


def test_prompt_hash_different_inputs() -> None:
    a = build_text_to_image_prompt("Cube", "a gray cube")
    b = build_text_to_image_prompt("Sphere", "a red sphere")
    assert _prompt_hash(a) != _prompt_hash(b)


def test_prompt_hash_length() -> None:
    h = _prompt_hash(build_text_to_image_prompt("Cube", "a gray stone cube"))
    assert len(h) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", h)


def test_build_prompt_content() -> None:
    prompt = build_text_to_image_prompt("Fire Sword", "a silver iron sword with black hilt")
    assert "Fire Sword" in prompt
    assert "silver iron sword" in prompt
    assert "contrasting solid background color" in prompt


def test_build_prompt_no_double_commas() -> None:
    prompt = build_text_to_image_prompt("Test", "a gray stone cube")
    assert ",," not in prompt
    assert ", ," not in prompt


def test_get_cached_sprite_path() -> None:
    prompt = build_text_to_image_prompt("Cube", "a gray stone cube")
    path = get_cached_sprite_path(prompt)
    assert path.suffix == ".png"
    assert path.parent == STATIC_DIR / "sprites"


def test_get_cached_sprite_path_deterministic() -> None:
    prompt = build_text_to_image_prompt("Cube", "a gray stone cube")
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
