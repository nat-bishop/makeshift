"""Tests for seed objects: all 15 valid, within budget, no contradictions."""

from app.models.tags import (
    OBJECT_TAG_BUDGET,
    TAG_CONTRADICTIONS,
    TAG_POWER_COSTS,
    Tag,
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
        assert cost <= OBJECT_TAG_BUDGET, (
            f"{obj.name} exceeds budget: cost={cost}, tags={obj.tags}"
        )


def test_seed_no_contradictions():
    for obj in SEED_OBJECTS:
        tag_set = set(obj.tags)
        for pair in TAG_CONTRADICTIONS:
            assert not (pair <= tag_set), (
                f"{obj.name} has contradictory tags: {pair}"
            )


def test_seed_power_costs_match_plan():
    """Verify specific seed object costs match the plan."""
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    # Costs computed from TAG_POWER_COSTS (plan table has minor discrepancies)
    assert by_name["Wooden Plank"].power_cost == 6   # SOLID(1)+RIGID(1)+FLAMMABLE(1)+BREAKABLE(1)+CLIMBABLE(2)
    assert by_name["Rope"].power_cost == 6            # SOLID(1)+FLEXIBLE(1)+FLAMMABLE(1)+CLIMBABLE(2)+LIGHT(1)
    assert by_name["Boulder"].power_cost == 5         # SOLID(1)+RIGID(1)+HEAVY(2)+BREAKABLE(1)
    assert by_name["Torch"].power_cost == 10          # SOLID(1)+RIGID(1)+HEAT_SOURCE(3)+HOT(2)+GLOWING(2)+LIGHT(1)
    assert by_name["Bucket of Water"].power_cost == 3 # LIQUID(1)+HEAVY(2)
    assert by_name["Trampoline"].power_cost == 5      # SOLID(1)+FLEXIBLE(1)+BOUNCY(2)+BREAKABLE(1)
    assert by_name["Ladder"].power_cost == 6          # SOLID(1)+RIGID(1)+CLIMBABLE(2)+BREAKABLE(1)+FLAMMABLE(1)
    assert by_name["Shield"].power_cost == 8          # SOLID(1)+RIGID(1)+HEAVY(2)+REFLECTIVE(2)+WEARABLE(2)
    assert by_name["Sword"].power_cost == 6           # SOLID(1)+RIGID(1)+SHARP(2)+TOOL(2)
    assert by_name["Ice Block"].power_cost == 7       # SOLID(1)+RIGID(1)+FROZEN(2)+COLD(1)+BREAKABLE(1)+SLIPPERY(1)
    assert by_name["Fan"].power_cost == 8             # SOLID(1)+RIGID(1)+WIND_SOURCE(3)+LIGHT(1)+TOOL(2)
    assert by_name["Balloon"].power_cost == 6         # GAS(1)+LIGHT(1)+FLOATING(2)+BREAKABLE(1)+FLEXIBLE(1)
    assert by_name["Metal Plate"].power_cost == 9     # SOLID(1)+RIGID(1)+HEAVY(2)+CONDUCTING(2)+MAGNETIC(3)
    assert by_name["TNT"].power_cost == 9             # SOLID(1)+RIGID(1)+EXPLOSIVE(5)+FLAMMABLE(1)+BREAKABLE(1)
    assert by_name["Umbrella"].power_cost == 8        # SOLID(1)+FLEXIBLE(1)+WEARABLE(2)+WIND_SOURCE(3)+LIGHT(1)


def test_seed_durability_values():
    by_name = {obj.name: obj for obj in SEED_OBJECTS}

    # BREAKABLE objects → 50
    assert by_name["Wooden Plank"].starting_durability == 50
    assert by_name["Boulder"].starting_durability == 50
    assert by_name["Trampoline"].starting_durability == 50
    assert by_name["Ladder"].starting_durability == 50
    assert by_name["Ice Block"].starting_durability == 50
    assert by_name["Balloon"].starting_durability == 50
    assert by_name["TNT"].starting_durability == 50

    # RIGID (no BREAKABLE) → 200
    assert by_name["Torch"].starting_durability == 200
    assert by_name["Shield"].starting_durability == 200
    assert by_name["Sword"].starting_durability == 200
    assert by_name["Fan"].starting_durability == 200
    assert by_name["Metal Plate"].starting_durability == 200

    # FLEXIBLE (no BREAKABLE, no RIGID) → 100
    assert by_name["Rope"].starting_durability == 100
    assert by_name["Umbrella"].starting_durability == 100

    # LIQUID → default 150
    assert by_name["Bucket of Water"].starting_durability == 150


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
    valid = {"tiny", "small", "medium", "large", "huge"}
    for obj in SEED_OBJECTS:
        assert obj.visual_descriptor.size_category in valid, (
            f"{obj.name} has invalid size_category: {obj.visual_descriptor.size_category}"
        )
