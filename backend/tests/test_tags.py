"""Tests for the tag system: enum completeness, contradictions."""

from app.models.tags import (
    TAG_CONTRADICTIONS,
    Tag,
)


def test_tag_count():
    """There should be exactly 29 tags."""
    assert len(Tag) == 29


def test_contradiction_pairs_are_frozensets_of_two():
    for pair in TAG_CONTRADICTIONS:
        assert isinstance(pair, frozenset)
        assert len(pair) == 2, f"Contradiction pair has {len(pair)} elements: {pair}"
        for t in pair:
            assert isinstance(t, Tag), f"{t} is not a Tag"


def test_contradiction_count():
    """There should be exactly 13 contradiction pairs."""
    assert len(TAG_CONTRADICTIONS) == 13


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
