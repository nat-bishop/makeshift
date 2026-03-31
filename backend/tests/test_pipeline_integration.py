"""Tests for pipeline async functions: sprite generation and caching."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app.images.pipeline as pipeline
import pytest
from app.images.pipeline import (
    SpriteResult,
    build_prompt,
    generate_sprite,
    generate_static_sprite,
    get_cached_sprite_path,
)
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag
from PIL import Image


@pytest.fixture(autouse=True)
def _reset_singletons():
    orig_gen = pipeline._generate_image
    orig_bg = pipeline._remove_bg
    pipeline._generate_image = None
    pipeline._remove_bg = None
    yield
    pipeline._generate_image = orig_gen
    pipeline._remove_bg = orig_bg


def _make_png(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGBA", (width, height), (255, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blueprint(id: str = "test-id", name: str = "Test Object") -> GameObjectBlueprint:
    return GameObjectBlueprint(
        id=id,
        name=name,
        description="test",
        tags=[Tag.RIGID, Tag.HEAVY],
        visual_descriptor=VisualDescriptor(
            visual_description="a gray cube", size_category="medium"
        ),
    )


class TestGenerateStaticSprite:
    async def test_generates_valid_512_png(self):
        raw_png = _make_png()
        pipeline._generate_image = AsyncMock(return_value=raw_png)
        pipeline._remove_bg = AsyncMock(return_value=raw_png)

        result = await generate_static_sprite("test")

        assert result[:4] == b"\x89PNG"
        img = Image.open(io.BytesIO(result))
        assert img.size == (512, 512)


class TestGenerateSprite:
    async def test_cache_hit(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
        cache_path = get_cached_sprite_path(prompt)

        sprites_dir = tmp_path / "sprites"
        sprites_dir.mkdir()
        (sprites_dir / cache_path.name).write_bytes(_make_png())

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch("app.config.settings") as mock_settings,
            patch.object(pipeline, "generate_static_sprite", new_callable=AsyncMock) as mock_gen,
        ):
            mock_settings.sprite_cache_enabled = True
            result = await generate_sprite(blueprint)

        assert isinstance(result, SpriteResult)
        assert cache_path.name in result.sprite_url
        mock_gen.assert_not_called()

    async def test_cache_miss_generates_and_writes(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
        cache_path = get_cached_sprite_path(prompt)
        png_bytes = _make_png()

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch("app.config.settings") as mock_settings,
            patch.object(
                pipeline, "generate_static_sprite", new_callable=AsyncMock, return_value=png_bytes
            ),
        ):
            mock_settings.sprite_cache_enabled = True
            result = await generate_sprite(blueprint)

        assert isinstance(result, SpriteResult)
        assert (tmp_path / "sprites" / cache_path.name).exists()

    async def test_returns_none_on_error(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        pipeline._generate_image = AsyncMock(side_effect=RuntimeError("boom"))
        pipeline._remove_bg = AsyncMock()

        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch("app.config.settings") as mock_settings,
        ):
            mock_settings.sprite_cache_enabled = True
            result = await generate_sprite(blueprint)

        assert result is None

    async def test_cache_disabled_skips_existing(self, tmp_path: Path) -> None:
        blueprint = _make_blueprint()
        prompt = build_prompt(blueprint.name, blueprint.visual_descriptor)
        cache_path = get_cached_sprite_path(prompt)

        sprites_dir = tmp_path / "sprites"
        sprites_dir.mkdir()
        (sprites_dir / cache_path.name).write_bytes(b"old")

        png_bytes = _make_png()
        with (
            patch.object(pipeline, "STATIC_DIR", tmp_path),
            patch("app.config.settings") as mock_settings,
            patch.object(
                pipeline, "generate_static_sprite", new_callable=AsyncMock, return_value=png_bytes
            ) as mock_gen,
        ):
            mock_settings.sprite_cache_enabled = False
            result = await generate_sprite(blueprint)

        assert result is not None
        mock_gen.assert_called_once()
