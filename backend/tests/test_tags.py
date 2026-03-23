"""Tests for the tag system: enum completeness, costs, contradictions, constants."""

from app.models.tags import (
    EQUIP_SLOT_MAP,
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    TRANSFERABLE_TAGS,
    Tag,
)


def test_tag_count():
    """There should be exactly 33 tags."""
    assert len(Tag) == 33


def test_every_tag_has_a_cost():
    """Every tag in the enum must have an entry in TAG_POWER_COSTS."""
    for tag in Tag:
        assert tag in TAG_POWER_COSTS, f"{tag} missing from TAG_POWER_COSTS"


def test_costs_are_positive_integers():
    for tag, cost in TAG_POWER_COSTS.items():
        assert isinstance(cost, int)
        assert 1 <= cost <= 5, f"{tag} has invalid cost {cost}"


def test_contradiction_pairs_are_frozensets_of_two():
    for pair in TAG_CONTRADICTIONS:
        assert isinstance(pair, frozenset)
        assert len(pair) == 2, f"Contradiction pair has {len(pair)} elements: {pair}"
        for t in pair:
            assert isinstance(t, Tag), f"{t} is not a Tag"


def test_contradiction_count():
    """There should be exactly 14 contradiction pairs."""
    assert len(TAG_CONTRADICTIONS) == 14


def test_no_self_contradictions():
    """No tag should contradict itself."""
    for pair in TAG_CONTRADICTIONS:
        tags = list(pair)
        assert tags[0] != tags[1]


def test_object_tag_budget():
    assert OBJECT_TAG_BUDGET == 10


def test_equip_slot_map_values():
    valid_slots = set(EQUIP_SLOT_MAP.values())
    for form, slot in EQUIP_SLOT_MAP.items():
        assert slot in valid_slots, f"{form} maps to invalid slot {slot}"


def test_transferable_tags_are_valid():
    for tag in TRANSFERABLE_TAGS:
        assert isinstance(tag, Tag)


def test_cost_1_tags():
    cost_1 = [t for t, c in TAG_POWER_COSTS.items() if c == 1]
    assert len(cost_1) == 10


def test_cost_2_tags():
    cost_2 = [t for t, c in TAG_POWER_COSTS.items() if c == 2]
    assert len(cost_2) == 14


def test_cost_3_tags():
    cost_3 = [t for t, c in TAG_POWER_COSTS.items() if c == 3]
    assert len(cost_3) == 4


def test_cost_4_tags():
    cost_4 = [t for t, c in TAG_POWER_COSTS.items() if c == 4]
    assert len(cost_4) == 4


def test_cost_5_tags():
    cost_5 = [t for t, c in TAG_POWER_COSTS.items() if c == 5]
    assert len(cost_5) == 1
    assert Tag.EXPLOSIVE in [t for t, c in TAG_POWER_COSTS.items() if c == 5]
