"""Tests for the V2 tag system: enum completeness, contradictions, V2 visible set."""

from app.models.tags import (
    LLM_VISIBLE_TAGS_V2,
    TAG_CONTRADICTIONS,
    Tag,
)


def test_tag_count():
    """There should be exactly 31 tags."""
    assert len(Tag) == 31


def test_v2_visible_tag_count():
    """V2 LLM picks from 12 tags."""
    assert len(LLM_VISIBLE_TAGS_V2) == 12


def test_v2_tags_are_subset_of_all_tags():
    for tag in LLM_VISIBLE_TAGS_V2:
        assert tag in Tag


def test_internal_tags_not_in_v2():
    assert Tag.HOT not in LLM_VISIBLE_TAGS_V2
    assert Tag.GLOWING not in LLM_VISIBLE_TAGS_V2
    assert Tag.BRITTLE not in LLM_VISIBLE_TAGS_V2
    assert Tag.CORRODED not in LLM_VISIBLE_TAGS_V2
    # Substance-absorbed tags not in V2
    assert Tag.RIGID not in LLM_VISIBLE_TAGS_V2
    assert Tag.METALLIC not in LLM_VISIBLE_TAGS_V2
    assert Tag.LIQUID not in LLM_VISIBLE_TAGS_V2
    assert Tag.FLAMMABLE not in LLM_VISIBLE_TAGS_V2


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
