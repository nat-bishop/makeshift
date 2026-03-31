"""Tests for the tag system: enum completeness, contradictions."""

from app.models.tags import (
    TAG_CONTRADICTIONS,
    Tag,
)


def test_tag_count():
    """There should be exactly 31 tags (27 LLM-visible + 4 internal)."""
    assert len(Tag) == 31


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
    """No tag should contradict itself."""
    for pair in TAG_CONTRADICTIONS:
        tags = list(pair)
        assert tags[0] != tags[1]


def test_wet_tag_exists():
    assert Tag.WET in Tag


def test_wet_contradictions():
    pairs = {frozenset(p) for p in TAG_CONTRADICTIONS}
    assert frozenset({Tag.WET, Tag.MOLTEN}) in pairs
    assert frozenset({Tag.WET, Tag.HEAT_SOURCE}) in pairs


def test_brittle_contradictions():
    pairs = {frozenset(p) for p in TAG_CONTRADICTIONS}
    assert frozenset({Tag.BRITTLE, Tag.LIQUID}) in pairs
    assert frozenset({Tag.BRITTLE, Tag.GAS}) in pairs


def test_internal_tags_not_llm_visible():
    from app.models.tags import LLM_VISIBLE_TAGS

    assert Tag.HOT not in LLM_VISIBLE_TAGS
    assert Tag.GLOWING not in LLM_VISIBLE_TAGS
    assert Tag.BRITTLE not in LLM_VISIBLE_TAGS
    assert Tag.CORRODED not in LLM_VISIBLE_TAGS


def test_auto_corrections_for_internal_tags():
    from app.models.tags import TAG_AUTO_CORRECTIONS

    assert TAG_AUTO_CORRECTIONS["BRITTLE"] == Tag.FROZEN
    assert TAG_AUTO_CORRECTIONS["CORRODED"] == Tag.ACIDIC
