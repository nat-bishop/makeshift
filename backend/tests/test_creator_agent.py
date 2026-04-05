"""Tests for create_object() — fallback behavior and blueprint structure."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.creator.agent import create_object
from app.models.blueprint import CreatorOutput, VisualDescriptor
from app.models.substances import Element, Substance
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
        substance=Substance.METAL,
        element=Element.BURNING,
        tags=[Tag.SHARP],
        visual_descriptor=VisualDescriptor(
            visual_description="a curved steel sword with a fiery red blade wreathed in flames",
            size_category="medium",
        ),
    )


async def test_fallback_on_llm_error() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.name == "Mysterious Fire Sword"
    assert bp.substance == Substance.STONE


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
    assert "stone" in v.visual_description or "cube" in v.visual_description
    assert v.size_category == "medium"


async def test_fallback_no_behaviors() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.behaviors == []


async def test_success_returns_v2_blueprint() -> None:
    output = _sample_creator_output()
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_success(output)):
        bp = await create_object("fire sword")
    assert bp.name == "Fire Sword"
    assert bp.substance == Substance.METAL
    assert Tag.SHARP in bp.tags
    assert Tag.METALLIC in bp.tags  # derived from metal substance
    assert Tag.HEAT_SOURCE in bp.tags  # derived from burning element


async def test_blueprint_has_uuid() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("test")
    uuid.UUID(bp.id)


async def test_blueprint_description_matches_input() -> None:
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_error()):
        bp = await create_object("fire sword")
    assert bp.description == "fire sword"


async def test_agent_called_with_description() -> None:
    agent = _mock_agent_success(_sample_creator_output())
    with patch("app.creator.agent._get_agent", return_value=agent):
        await create_object("magic wand")
    agent.run.assert_called_once_with("Create a game object for: magic wand")


async def test_substance_profile_in_blueprint() -> None:
    output = _sample_creator_output()
    with patch("app.creator.agent._get_agent", return_value=_mock_agent_success(output)):
        bp = await create_object("fire sword")
    assert "mass" in bp.substance_profile
    assert "melee_damage" in bp.combat_profile
    assert bp.starting_durability == 250  # metal durability
