"""Tests for create_object() — fallback behavior and blueprint structure."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.creator.agent import create_object
from app.models.blueprint import CreatorOutput, VisualDescriptor
from app.models.tags import Tag


def _mock_agent_error(error: Exception | None = None) -> MagicMock:
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=error or Exception("LLM timeout"))
    return agent


def _mock_agent_success(output: CreatorOutput) -> MagicMock:
    result = MagicMock()
    result.output = output
    agent = MagicMock()
    agent.run = AsyncMock(return_value=result)
    return agent


def _sample_creator_output() -> CreatorOutput:
    return CreatorOutput(
        name="Fire Sword",
        tags=[Tag.SOLID, Tag.SHARP, Tag.HEAT_SOURCE],
        visual_descriptor=VisualDescriptor(
            base_form="sword",
            material="metal",
            color_primary="#CC3300",
            color_primary_name="fiery red",
            color_secondary="#FF6600",
            color_secondary_name="bright orange",
            visual_effects=["flaming"],
            size_category="medium",
            bg_color="#4A6741",
        ),
    )


async def test_fallback_on_llm_error() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.name == "Mysterious Fire Sword"
    assert bp.tags == [Tag.SOLID, Tag.RIGID]


async def test_fallback_name_two_words() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("big red dragon")
    assert bp.name == "Mysterious Big Red"


async def test_fallback_name_single_word() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("sword")
    assert bp.name == "Mysterious Sword"


async def test_fallback_empty_description() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("")
    assert bp.name == "Mysterious Object"


async def test_fallback_visual_defaults() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("anything")
    v = bp.visual_descriptor
    assert v.base_form == "cube"
    assert v.material == "stone"
    assert v.color_primary == "#888888"
    assert v.color_primary_name == "gray"
    assert v.color_secondary == "#666666"
    assert v.color_secondary_name == "dark gray"
    assert v.visual_effects == ["sparkling"]
    assert v.size_category == "medium"
    assert v.bg_color == "#4A6741"


async def test_fallback_no_behaviors() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.behaviors == []


async def test_success_returns_llm_output() -> None:
    output = _sample_creator_output()
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_success(output)):
        bp = await create_object("fire sword")
    assert bp.name == "Fire Sword"
    assert bp.tags == [Tag.SOLID, Tag.SHARP, Tag.HEAT_SOURCE]


async def test_blueprint_has_uuid() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("test")
    uuid.UUID(bp.id)  # raises ValueError if not valid UUID


async def test_blueprint_description_matches_input() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.description == "fire sword"


async def test_agent_called_with_description() -> None:
    agent = _mock_agent_success(_sample_creator_output())
    with patch("app.creator.agent._get_agent", return_value=agent):
        await create_object("magic wand")
    agent.run.assert_called_once_with("Create a game object for: magic wand")
