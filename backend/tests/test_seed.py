"""Tests for seed objects: all 15 valid, within budget, no contradictions."""

from app.models.blueprint import (
    DURABILITY_BREAKABLE,
    DURABILITY_DEFAULT,
    DURABILITY_FLEXIBLE,
    DURABILITY_RIGID,
)
from app.models.tags import (
    OBJECT_TAG_BUDGET,
    SIZE_PIXEL_MAP,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
)
from app.seed.objects import SEED_OBJECTS


def test_seed_count():
    """There should be exactly 15 seed objects."""
    assert len(SEED_OBJECTS) == 15


def test_seed_unique_ids():
    ids = [obj.id for obj in SEED_OBJECTS]
    assert len(ids) == len(set(ids)), "Duplicate seed object IDs"


def test_seed_unique_names():
    names = [obj.name for obj in SEED_OBJECTS]
    assert len(names) == len(set(names)), "Duplicate seed object names"


def test_seed_within_budget():
    for obj in SEED_OBJECTS:
        cost = sum(TAG_POWER_COSTS[t] for t in obj.tags)
        assert cost <= OBJECT_TAG_BUDGET, f"{obj.name} exceeds budget: cost={cost}, tags={obj.tags}"


def test_seed_no_contradictions():
    for obj in SEED_OBJECTS:
        tag_set = set(obj.tags)
        for pair in TAG_CONTRADICTIONS:
            assert not (pair <= tag_set), f"{obj.name} has contradictory tags: {pair}"


def test_seed_power_costs_match_plan():
    """Verify specific seed object costs match the plan."""
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    # Costs computed from TAG_POWER_COSTS
    assert by_name["Wooden Plank"].power_cost == 6
    assert by_name["Rope"].power_cost == 6
    assert by_name["Boulder"].power_cost == 5
    assert by_name["Torch"].power_cost == 10
    assert by_name["Bucket of Water"].power_cost == 3
    assert by_name["Trampoline"].power_cost == 5
    assert by_name["Ladder"].power_cost == 6
    assert by_name["Shield"].power_cost == 8
    assert by_name["Sword"].power_cost == 6
    assert by_name["Ice Block"].power_cost == 7
    assert by_name["Fan"].power_cost == 8
    assert by_name["Balloon"].power_cost == 6
    assert by_name["Metal Plate"].power_cost == 9
    assert by_name["TNT"].power_cost == 9
    assert by_name["Umbrella"].power_cost == 8


def test_seed_durability_values():
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    # BREAKABLE objects
    assert by_name["Wooden Plank"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["Boulder"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["Trampoline"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["Ladder"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["Ice Block"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["Balloon"].starting_durability == DURABILITY_BREAKABLE
    assert by_name["TNT"].starting_durability == DURABILITY_BREAKABLE

    # RIGID (no BREAKABLE)
    assert by_name["Torch"].starting_durability == DURABILITY_RIGID
    assert by_name["Shield"].starting_durability == DURABILITY_RIGID
    assert by_name["Sword"].starting_durability == DURABILITY_RIGID
    assert by_name["Fan"].starting_durability == DURABILITY_RIGID
    assert by_name["Metal Plate"].starting_durability == DURABILITY_RIGID

    # FLEXIBLE (no BREAKABLE, no RIGID)
    assert by_name["Rope"].starting_durability == DURABILITY_FLEXIBLE
    assert by_name["Umbrella"].starting_durability == DURABILITY_FLEXIBLE

    # LIQUID → default
    assert by_name["Bucket of Water"].starting_durability == DURABILITY_DEFAULT


def test_seed_equippable_objects():
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    # WEARABLE or TOOL
    assert by_name["Shield"].is_equippable is True
    assert by_name["Sword"].is_equippable is True
    assert by_name["Fan"].is_equippable is True
    assert by_name["Umbrella"].is_equippable is True

    # Not equippable
    assert by_name["Wooden Plank"].is_equippable is False
    assert by_name["Boulder"].is_equippable is False
    assert by_name["Torch"].is_equippable is False


def test_seed_equip_slots():
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    assert by_name["Shield"].equip_slot == "back"
    assert by_name["Sword"].equip_slot == "hand"
    assert by_name["Fan"].equip_slot == "hand"


def test_seed_all_have_descriptions():
    for obj in SEED_OBJECTS:
        assert obj.description, f"{obj.name} has empty description"


def test_seed_all_have_valid_size_categories():
    valid = set(SIZE_PIXEL_MAP)
    for obj in SEED_OBJECTS:
        assert obj.visual_descriptor.size_category in valid, (
            f"{obj.name} has invalid size_category: {obj.visual_descriptor.size_category}"
        )
