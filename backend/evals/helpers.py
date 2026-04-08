"""Shared helpers for V3 LLM quality gate tests."""

from __future__ import annotations

from app.cache.store import normalize_name
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.models.state import State

# ---------------------------------------------------------------------------
# State string <-> integer code mapping (built from State enum to prevent drift)
# ---------------------------------------------------------------------------

STATE_STRING_TO_CODE: dict[str, int] = {}
for _s in State:
    STATE_STRING_TO_CODE[_s.name.lower()] = _s.value  # "on_fire" -> 1
    STATE_STRING_TO_CODE[f"remove_{_s.name.lower()}"] = _s.value + 7  # "remove_on_fire" -> 8

PUSH_PULL_MAP: dict[str, int] = {"push": 0, "pull": 1}

# ---------------------------------------------------------------------------
# Blueprint factory
# ---------------------------------------------------------------------------


def make_blueprint(
    name: str,
    *,
    autonomous: bool = False,
    mass_kg: float = 1.0,
    height_cm: int = 30,
    friction: int = 50,
    bounce: int = 10,
    gravity: int = 50,
    armor: int = 30,
    hp: int = 50,
    indestructible: bool = False,
    has_field: bool = False,
    field_range_cm: int = 0,
    affordance: int = 3,
) -> GameObjectBlueprint:
    """Build a minimal GameObjectBlueprint without LLM calls."""
    return GameObjectBlueprint(
        id=f"eval-{name}",
        name=name,
        description=name,
        visual_description=f"a {name}",
        physics=PhysicsProperties(
            mass_kg=mass_kg,
            height_cm=height_cm,
            friction=friction,
            bounce=bounce,
            gravity=gravity,
        ),
        destructibility=Destructibility(
            armor=armor,
            hp=hp,
            indestructible=indestructible,
        ),
        affordance=affordance,
        autonomous=autonomous,
        has_field=has_field,
        field_range_cm=field_range_cm,
    )


# ---------------------------------------------------------------------------
# Pair orientation helper
# ---------------------------------------------------------------------------

# Fields that are per-side (a/b) and need swapping when evaluate_pair reorders
_SIDE_FIELDS = {
    "damage_a": "damage_b",
    "damage_b": "damage_a",
    "state_a": "state_b",
    "state_b": "state_a",
    "destroy_a": "destroy_b",
    "destroy_b": "destroy_a",
    "force_a": "force_b",
    "force_b": "force_a",
}


def orient_expected(pair: list[str], expected: dict) -> dict:
    """Remap expected a/b fields to match evaluate_pair's sorted order.

    evaluate_pair() sorts A/B lexicographically by normalized name.
    Fixture pairs may list them in either order, so if the fixture's A
    sorts after B, we swap all a/b suffixed fields.
    """
    a, b = normalize_name(pair[0]), normalize_name(pair[1])
    if a <= b:
        return expected  # already in sorted order
    # Swap a/b fields
    swapped: dict = {}
    for k, v in expected.items():
        swapped[_SIDE_FIELDS.get(k, k)] = v
    return swapped
