"""Tests for pipeline async functions: sprite generation and caching."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import app.images.pipeline as pipeline
import pytest
from app.images.pipeline import (
    SpriteResult,
    generate_sprite,
    generate_static_sprite,
    get_cached_sprite_path,
)
from app.models.blueprint import GameObjectBlueprint, PhysicsProperties
from app.prompts.image import build_text_to_image_prompt
from PIL import Image

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_singletons():
    orig_bg = pipeline.remove_bg
    yield
    pipeline.remove_bg = orig_bg


def _make_png(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGBA", (width, height), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blueprint(id: str = "test-id", name: str = "test object") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=id,
        name=name,
        description="test",
        visual_description="a gray cube",
        physics=PhysicsProperties(mass_kg=5.0, height_cm=30, surface=1, bounce=10, gravity=50),
        durability=2,
    )


class TestGenerateStaticSprite:
    async def test_generates_valid_512_png(self):
        raw_png = _make_png()
        with (
            patch.object(pipeline, "generate_image", new=AsyncMock(return_value=raw_png)),
            patch.object(pipeline, "remove_bg", new=AsyncMock(return_value=raw_png)),
        ):
            result = await generate_static_sprite("test")

        assert result[:4] == b"\x89PNG"
        img = Image.open(io.BytesIO(result))
        assert img.size == (512, 512)


class TestGenerateSprite:
    async def test_cache_hit(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        prompt = build_text_to_image_prompt(blueprint.name, blueprint.visual_description)
        cache_path = get_cached_sprite_path(prompt)

        sprites_dir = tmp_path / "sprites"
        sprites_dir.mkdir()
        (sprites_dir / cache_path.name).write_bytes(_make_png())

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch.object(pipeline, "generate_static_sprite", new_callable=AsyncMock) as mock_gen,
        ):
            result = await generate_sprite(blueprint)

        assert isinstance(result, SpriteResult)
        assert cache_path.name in result.sprite_url
        mock_gen.assert_not_called()

    async def test_cache_miss_generates_and_writes(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        prompt = build_text_to_image_prompt(blueprint.name, blueprint.visual_description)
        cache_path = get_cached_sprite_path(prompt)
        png_bytes = _make_png()

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch.object(
                pipeline, "generate_static_sprite", new_callable=AsyncMock, return_value=png_bytes
            ),
        ):
            result = await generate_sprite(blueprint)

        assert isinstance(result, SpriteResult)
        assert (tmp_path / "sprites" / cache_path.name).exists()

    async def test_returns_none_on_error(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch.object(
                pipeline,
                "generate_static_sprite",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
        ):
            result = await generate_sprite(blueprint)

        assert result is None
