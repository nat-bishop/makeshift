"""Tests for the tag system: enum completeness, contradictions, LLM visible set."""

from app.models.tags import (
    BEHAVIOR_TARGETS,
    LLM_VISIBLE_TAGS,
    TAG_CONTRADICTIONS,
    Category,
    Tag,
)


def test_tag_count():
    """There should be exactly 31 tags."""
    assert len(Tag) == 31


def test_llm_visible_tag_count():
    """LLM picks from 10 tags (LIVING and HOSTILE are auto-derived)."""
    assert len(LLM_VISIBLE_TAGS) == 10


def test_llm_tags_are_subset_of_all_tags():
    for tag in LLM_VISIBLE_TAGS:
        assert tag in Tag


def test_internal_tags_not_in_llm_visible():
    assert Tag.HOT not in LLM_VISIBLE_TAGS
    assert Tag.GLOWING not in LLM_VISIBLE_TAGS
    assert Tag.BRITTLE not in LLM_VISIBLE_TAGS
    assert Tag.CORRODED not in LLM_VISIBLE_TAGS
    # Substance-absorbed tags not in LLM visible set
    assert Tag.RIGID not in LLM_VISIBLE_TAGS
    assert Tag.METALLIC not in LLM_VISIBLE_TAGS
    assert Tag.LIQUID not in LLM_VISIBLE_TAGS
    assert Tag.FLAMMABLE not in LLM_VISIBLE_TAGS
    # Auto-derived tags not in LLM visible set
    assert Tag.LIVING not in LLM_VISIBLE_TAGS
    assert Tag.HOSTILE not in LLM_VISIBLE_TAGS


def test_category_count():
    """There should be exactly 7 categories."""
    assert len(Category) == 7


def test_behavior_targets():
    """BEHAVIOR_TARGETS = categories + select state tags."""
    assert len(BEHAVIOR_TARGETS) == 9
    # Categories
    assert "CREATURE" in BEHAVIOR_TARGETS
    assert "FOOD" in BEHAVIOR_TARGETS
    assert "VALUABLE" in BEHAVIOR_TARGETS
    # State tags used as behavior targets
    assert "HOSTILE" in BEHAVIOR_TARGETS
    assert "HEAT_SOURCE" in BEHAVIOR_TARGETS


def test_contradiction_pairs_are_frozensets_of_two():
    for pair in TAG_CONTRADICTIONS:
        assert isinstance(pair, frozenset)
        assert len(pair) == 2, f"Contradiction pair has {len(pair)} elements: {pair}"
        for t in pair:
            assert isinstance(t, Tag), f"{t} is not a Tag"


def test_contradiction_count():
    """There should be exactly 16 contradiction pairs."""
    assert len(TAG_CONTRADICTIONS) == 16


def test_no_self_contradictions():
    for pair in TAG_CONTRADICTIONS:
        tags = list(pair)
        assert tags[0] != tags[1]


def test_wet_contradictions():
    pairs = {frozenset(p) for p in TAG_CONTRADICTIONS}
    assert frozenset({Tag.WET, Tag.MOLTEN}) in pairs
    assert frozenset({Tag.WET, Tag.HEAT_SOURCE}) in pairs


def test_brittle_contradictions():
    pairs = {frozenset(p) for p in TAG_CONTRADICTIONS}
    assert frozenset({Tag.BRITTLE, Tag.LIQUID}) in pairs
    assert frozenset({Tag.BRITTLE, Tag.GAS}) in pairs
