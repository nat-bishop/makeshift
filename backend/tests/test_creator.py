"""Tests for creator agent: system prompt, fallback logic."""

import uuid

from app.creator.agent import SYSTEM_PROMPT
from app.models.behaviors import (
    LLM_VISIBLE_ACTIONS,
    LLM_VISIBLE_TRIGGERS,
)
from app.models.blueprint import (
    DURABILITY_RIGID,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import LLM_VISIBLE_TAGS, Tag


def make_visual(**kwargs: object) -> VisualDescriptor:
    defaults: dict[str, object] = {
        "visual_description": "a gray stone cube",
        "size_category": "medium",
    }
    defaults.update(kwargs)
    return VisualDescriptor(**defaults)  # type: ignore[arg-type]


def test_system_prompt_contains_all_llm_visible_tags():
    """System prompt should mention every LLM-visible tag."""
    for tag in LLM_VISIBLE_TAGS:
        assert tag.value in SYSTEM_PROMPT, f"Tag {tag.value} not in system prompt"


def test_system_prompt_mentions_contradictions():
    assert "FROZEN" in SYSTEM_PROMPT
    assert "MOLTEN" in SYSTEM_PROMPT
    assert "contradict" in SYSTEM_PROMPT.lower() or "Contradictions" in SYSTEM_PROMPT


def test_fallback_object_structure():
    """Verify the fallback object matches expected shape."""
    vd = make_visual()
    fallback = CreatorOutput(
        name="Mysterious Fire Sword",
        tags=[Tag.RIGID, Tag.SHARP],
        visual_descriptor=vd,
    )
    bp = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=fallback.name,
        description="fire sword",
        tags=fallback.tags,
        visual_descriptor=fallback.visual_descriptor,
    )
    assert bp.starting_durability == DURABILITY_RIGID


def test_system_prompt_mentions_all_triggers() -> None:
    """System prompt should document all LLM-visible behavior triggers."""
    for trigger in LLM_VISIBLE_TRIGGERS:
        assert trigger.value in SYSTEM_PROMPT, f"Missing trigger: {trigger.value}"


def test_system_prompt_mentions_all_actions() -> None:
    """System prompt should document all LLM-visible behavior actions."""
    for action in LLM_VISIBLE_ACTIONS:
        assert action.value in SYSTEM_PROMPT, f"Missing action: {action.value}"


def test_fallback_object_is_valid_creator_output() -> None:
    """The fallback object used when LLM fails should validate as CreatorOutput."""
    co = CreatorOutput(
        name="Mysterious Object",
        tags=[Tag.RIGID, Tag.BREAKABLE],
        visual_descriptor=make_visual(),
    )
    assert co.name == "Mysterious Object"
    assert len(co.tags) == 2
