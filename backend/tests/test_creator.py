"""Tests for creator agent: system prompt, fallback logic."""

import uuid

from app.creator.agent import SYSTEM_PROMPT
from app.models.blueprint import CreatorOutput, GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag


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
    assert "contradict" in SYSTEM_PROMPT.lower() or "cannot coexist" in SYSTEM_PROMPT.lower()


def test_fallback_object_structure():
    """Verify the fallback object matches expected shape."""
    fallback = CreatorOutput(
        name="Mysterious Fire Sword",
        tags=[Tag.SOLID, Tag.RIGID],
        visual_descriptor=VisualDescriptor(
            base_form="cube",
            material="stone",
            color_primary="#888888",
            color_secondary="#666666",
            visual_effects=["sparkling"],
            size_category="medium",
        ),
    )
    bp = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=fallback.name,
        description="fire sword",
        tags=fallback.tags,
        visual_descriptor=fallback.visual_descriptor,
    )
    assert bp.power_cost == 2  # SOLID(1) + RIGID(1)
    assert bp.is_equippable is False
    assert bp.starting_durability == 200  # RIGID
