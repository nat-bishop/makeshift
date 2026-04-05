"""Tests for creator agent: system prompt, fallback logic."""

import uuid

from app.creator.agent import SYSTEM_PROMPT
from app.models.blueprint import (
    BehaviorVerb,
    CreatorOutput,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.substances import Element, Substance
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


def test_system_prompt_mentions_all_substances():
    for s in Substance:
        assert s.value in SYSTEM_PROMPT, f"Substance {s.value} not in system prompt"


def test_system_prompt_mentions_all_elements():
    for e in Element:
        assert e.value in SYSTEM_PROMPT, f"Element {e.value} not in system prompt"


def test_system_prompt_mentions_all_verbs():
    for v in BehaviorVerb:
        assert v.value in SYSTEM_PROMPT, f"Verb {v.value} not in system prompt"


def test_fallback_object_structure():
    """Verify the fallback object matches expected shape."""
    vd = make_visual()
    fallback = CreatorOutput(
        name="Mysterious Rock",
        substance=Substance.STONE,
        tags=[],
        visual_descriptor=vd,
    )
    bp = GameObjectBlueprint(
        id=str(uuid.uuid4()),
        name=fallback.name,
        description="rock",
        substance=fallback.substance,
        tags=[Tag.RIGID, Tag.HEAVY],
        visual_descriptor=fallback.visual_descriptor,
        starting_durability=300,
    )
    assert bp.starting_durability == 300
    assert bp.substance == Substance.STONE


def test_fallback_object_is_valid_creator_output() -> None:
    co = CreatorOutput(
        name="Mysterious Object",
        substance=Substance.STONE,
        tags=[],
        visual_descriptor=make_visual(),
    )
    assert co.name == "Mysterious Object"
    assert co.substance == Substance.STONE
