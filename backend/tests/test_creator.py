"""Tests for creator agent: system prompt, fallback logic."""

import uuid

from app.creator.agent import SYSTEM_PROMPT
from app.models.behaviors import BehaviorAction, BehaviorTrigger
from app.models.blueprint import (
    DURABILITY_RIGID,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import Tag


def make_visual(**kwargs: object) -> VisualDescriptor:
    defaults: dict[str, object] = {
        "visual_description": "a gray stone cube",
        "size_category": "medium",
    }
    defaults.update(kwargs)
    return VisualDescriptor(**defaults)  # type: ignore[arg-type]


def test_system_prompt_contains_all_tags():
    """System prompt should mention every tag."""
    for tag in Tag:
        assert tag.value in SYSTEM_PROMPT, f"Tag {tag.value} not in system prompt"


def test_system_prompt_mentions_budget():
    assert "10" in SYSTEM_PROMPT
    assert "budget" in SYSTEM_PROMPT.lower()


def test_system_prompt_mentions_contradictions():
    assert "FROZEN" in SYSTEM_PROMPT
    assert "MOLTEN" in SYSTEM_PROMPT
    assert "contradict" in SYSTEM_PROMPT.lower() or "Contradictions" in SYSTEM_PROMPT


def test_fallback_object_structure():
    """Verify the fallback object matches expected shape."""
    vd = make_visual()
    fallback = CreatorOutput(
        name="Mysterious Fire Sword",
        tags=[Tag.SOLID, Tag.RIGID],
        visual_descriptor=vd,
    )
    bp = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=fallback.name,
        description="fire sword",
        tags=fallback.tags,
        visual_descriptor=fallback.visual_descriptor,
    )
    assert bp.power_cost == 2  # SOLID(1) + RIGID(1)
    assert bp.starting_durability == DURABILITY_RIGID


def test_system_prompt_mentions_all_triggers() -> None:
    """System prompt should document all behavior triggers."""
    for trigger in BehaviorTrigger:
        assert trigger.value in SYSTEM_PROMPT, f"Missing trigger: {trigger.value}"


def test_system_prompt_mentions_all_actions() -> None:
    """System prompt should document all behavior actions."""
    for action in BehaviorAction:
        assert action.value in SYSTEM_PROMPT, f"Missing action: {action.value}"


def test_fallback_object_is_valid_creator_output() -> None:
    """The fallback object used when LLM fails should validate as CreatorOutput."""
    co = CreatorOutput(
        name="Mysterious Object",
        tags=[Tag.SOLID, Tag.RIGID],
        visual_descriptor=make_visual(),
    )
    assert co.name == "Mysterious Object"
    assert len(co.tags) == 2
