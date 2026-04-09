"""Tests for the V3 creator pipeline (backend/app/creator/pipeline.py).

Covers cache hit/miss paths, name truncation/fallback, field gating,
destruction name parsing, and cache-disabled mode.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

from app.creator.pipeline import create_object

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# Shared answer dict returned by a mocked run_questions.
# `speed` is intentionally included — the pipeline ignores unknown keys,
# and this verifies extra answers don't cause errors.
_BASE_ANSWERS: dict[str, object] = {
    "mass_kg": 1.5,
    "height_cm": 120,
    "surface": 1,
    "bounce": 10,
    "gravity": 50,
    "has_field": False,
    "durability": 2,
    "autonomous": False,
    "affordance": 0,
    "visual_description": "a flaming steel sword",
    "speed": 2,
}


def _make_cache(get_return: dict | None = None) -> AsyncMock:
    """Build an AsyncMock CacheStore with configurable get_creation return."""
    cache = AsyncMock()
    cache.get_creation = AsyncMock(return_value=get_return)
    cache.put_creation = AsyncMock()
    return cache


@asynccontextmanager
async def _pipeline_mocks(
    *,
    name: str = "Object",
    answers: dict | None = None,
    cache_enabled: bool = False,
) -> AsyncIterator[None]:
    """Patch the pipeline's LLM calls and settings for a single test."""
    with (
        patch("app.creator.pipeline.settings") as mock_settings,
        patch("app.creator.pipeline.ask_text", new_callable=AsyncMock, return_value=name),
        patch(
            "app.creator.pipeline.run_questions",
            new_callable=AsyncMock,
            return_value=answers if answers is not None else dict(_BASE_ANSWERS),
        ),
    ):
        mock_settings.creation_cache_enabled = cache_enabled
        mock_settings.llm_model = "test-model"
        yield


# ---------- 1. Cache hit path ----------


async def test_cache_hit_returns_cached_blueprint() -> None:
    cached_data = {
        "name": "Fire Sword",
        "visual_description": "a flaming steel sword",
        "physics": {"mass_kg": 1.5, "height_cm": 120, "surface": 1, "bounce": 10, "gravity": 50},
        "durability": 4,
        "affordance": 0,
        "autonomous": False,
        "has_field": False,
        "field_range_cm": 0,
        "destruction_result_name": "",
    }
    cache = _make_cache(get_return=cached_data)

    with (
        patch("app.creator.pipeline.settings") as mock_settings,
        patch("app.creator.pipeline.run_questions", new_callable=AsyncMock) as mock_rq,
    ):
        mock_settings.creation_cache_enabled = True
        bp = await create_object("fire sword", cache)

    assert bp.name == "Fire Sword"
    assert bp.durability == 4
    assert bp.description == "fire sword"
    assert bp.id  # fresh UUID on every call
    mock_rq.assert_not_awaited()


# ---------- 2. Full LLM pipeline (cache miss) ----------


async def test_full_pipeline_cache_miss() -> None:
    cache = _make_cache(get_return=None)

    async with _pipeline_mocks(name="Fire Sword", cache_enabled=True):
        bp = await create_object("fire sword", cache)

    assert bp.name == "Fire Sword"
    assert bp.physics.mass_kg == 1.5
    assert bp.physics.height_cm == 120
    assert bp.durability == 2
    assert bp.affordance == 0
    assert bp.autonomous is False
    assert bp.visual_description == "a flaming steel sword"
    cache.put_creation.assert_awaited_once()


# ---------- 3. Name truncation (>3 words) ----------


async def test_name_truncated_to_three_words() -> None:
    cache = _make_cache()

    async with _pipeline_mocks(name="A Very Long Name Indeed"):
        bp = await create_object("something", cache)

    assert bp.name == "A Very Long"


# ---------- 4. Empty name fallback (whitespace) ----------


async def test_empty_name_fallback_uses_description() -> None:
    cache = _make_cache()

    async with _pipeline_mocks(name="  "):
        bp = await create_object("magical sword", cache)

    assert bp.name == "Magical"


# ---------- 5. Empty description fallback ----------


async def test_empty_description_fallback_uses_object() -> None:
    cache = _make_cache()

    async with _pipeline_mocks(name=""):
        bp = await create_object("", cache)

    assert bp.name == "Object"


# ---------- 6. Destruction name parsing ----------


async def test_destruction_name_parsed() -> None:
    cache = _make_cache()
    answers = {**_BASE_ANSWERS, "destruction_result_name": "glass shards"}

    async with _pipeline_mocks(name="Glass Vase", answers=answers):
        bp = await create_object("glass vase", cache)

    assert bp.destruction_result_name == "glass shards"


async def test_destruction_name_nothing_becomes_empty() -> None:
    cache = _make_cache()
    answers = {**_BASE_ANSWERS, "destruction_result_name": "nothing"}

    async with _pipeline_mocks(name="Balloon", answers=answers):
        bp = await create_object("balloon", cache)

    assert bp.destruction_result_name == ""


async def test_destruction_name_none_becomes_empty() -> None:
    cache = _make_cache()
    answers = {**_BASE_ANSWERS, "destruction_result_name": "none"}

    async with _pipeline_mocks(name="Smoke", answers=answers):
        bp = await create_object("smoke", cache)

    assert bp.destruction_result_name == ""


# ---------- 7. has_field=False zeroes field_range_cm ----------


async def test_has_field_false_zeroes_field_range() -> None:
    cache = _make_cache()
    answers = {**_BASE_ANSWERS, "has_field": False, "field_range_cm": 200}

    async with _pipeline_mocks(name="Rock", answers=answers):
        bp = await create_object("rock", cache)

    assert bp.field_range_cm == 0
    assert bp.has_field is False


# ---------- 8. Cache disabled skips read and write ----------


async def test_cache_disabled_skips_read_and_write() -> None:
    cache = _make_cache()

    async with _pipeline_mocks(name="Sword"):
        bp = await create_object("sword", cache)

    assert bp.name == "Sword"
    cache.get_creation.assert_not_awaited()
    cache.put_creation.assert_not_awaited()
