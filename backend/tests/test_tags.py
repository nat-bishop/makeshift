"""Tests for the tag system: enum completeness, costs, contradictions, constants."""

import pytest
from app.models.tags import (
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    Tag,
)


def test_tag_count():
    """There should be exactly 30 tags."""
    assert len(Tag) == 30


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
    """There should be exactly 15 contradiction pairs."""
    assert len(TAG_CONTRADICTIONS) == 15


def test_no_self_contradictions():
    """No tag should contradict itself."""
    for pair in TAG_CONTRADICTIONS:
        tags = list(pair)
        assert tags[0] != tags[1]


def test_object_tag_budget():
    assert OBJECT_TAG_BUDGET == 10


@pytest.mark.parametrize(
    ("cost", "expected_count"),
    [(1, 10), (2, 11), (3, 4), (4, 4), (5, 1)],
)
def test_cost_distribution(cost: int, expected_count: int) -> None:
    actual = [t for t, c in TAG_POWER_COSTS.items() if c == cost]
    assert len(actual) == expected_count, (
        f"Cost {cost}: expected {expected_count}, got {len(actual)}"
    )
