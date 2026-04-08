"""Physics quality gate: does create_object() produce reasonable physics?

Calls the real creation pipeline for known objects and validates that the
blueprint's physics, classification, and affordance fields land in sensible ranges.

Run: make eval-physics
"""

from __future__ import annotations

import pytest
from app.cache.store import CacheStore
from app.creator.pipeline import create_object
from app.models.blueprint import GameObjectBlueprint

# ---------------------------------------------------------------------------
# Test cases: (description, material_key, extra_checks)
#
# material_key maps to physics_reference.yaml for range validation.
# extra_checks: {field: expected_value} for boolean/enum checks.
#   Nested fields use dot notation: "destructibility.indestructible"
# ---------------------------------------------------------------------------

PHYSICS_CASES: list[tuple[str, str, dict]] = [
    ("iron sword", "metal", {"autonomous": False, "affordance": 0}),
    ("wooden shield", "wood", {"autonomous": False}),
    ("campfire", "wood", {"has_field": True}),
    ("zombie", "flesh", {"autonomous": True}),
    ("glass bottle", "glass", {}),
    ("rubber ball", "rubber", {}),
    ("mountain", "stone", {"destructibility.indestructible": True}),
    ("ice cube", "ice", {}),
    ("horse", "flesh", {"autonomous": True, "affordance": 1}),
    ("ladder", "wood", {"affordance": 2}),
    ("lava pool", "lava", {"has_field": True}),
    ("feather", "cloth", {}),
    ("boulder", "stone", {}),
    ("smoke cloud", "smoke", {}),
    ("balloon", "cloth", {}),
]


def _ids(cases: list[tuple]) -> list[str]:
    return [c[0] for c in cases]


# ---------------------------------------------------------------------------
# Shared blueprint cache (session-scoped) to avoid duplicate LLM calls
# ---------------------------------------------------------------------------

_blueprint_cache: dict[str, GameObjectBlueprint] = {}


async def _get_blueprint(description: str, cache: CacheStore) -> GameObjectBlueprint:
    if description not in _blueprint_cache:
        _blueprint_cache[description] = await create_object(description, cache)
    return _blueprint_cache[description]


def _get_nested(obj: object, dotted_path: str) -> object:
    """Resolve dotted field path, e.g. 'destructibility.indestructible'."""
    result = obj
    for part in dotted_path.split("."):
        result = getattr(result, part)
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("description,material,extra", PHYSICS_CASES, ids=_ids(PHYSICS_CASES))
async def test_physics_ranges(
    description: str,
    material: str,
    extra: dict,
    cache: CacheStore,
    physics_reference: dict,
) -> None:
    """Validate physics properties fall within reference ranges (with tolerance)."""
    bp = await _get_blueprint(description, cache)
    ref = physics_reference[material]

    # Tolerance: widen range by 50%, clamped to field bounds
    def check_range(actual: float, lo: float, hi: float, field: str, bounds: tuple) -> None:
        margin = (hi - lo) * 0.5
        tol_lo = max(bounds[0], lo - margin)
        tol_hi = min(bounds[1], hi + margin)
        assert tol_lo <= actual <= tol_hi, (
            f"{description}: {field}={actual} outside [{tol_lo}, {tol_hi}] "
            f"(reference [{lo}, {hi}])"
        )

    check_range(bp.physics.mass_kg, ref["mass"][0], ref["mass"][1], "mass_kg", (0.001, 100000))
    check_range(bp.physics.friction, ref["friction"][0], ref["friction"][1], "friction", (0, 100))
    check_range(bp.physics.bounce, ref["bounce"][0], ref["bounce"][1], "bounce", (0, 100))
    check_range(bp.physics.gravity, ref["gravity"][0], ref["gravity"][1], "gravity", (0, 100))


@pytest.mark.parametrize("description,material,extra", PHYSICS_CASES, ids=_ids(PHYSICS_CASES))
async def test_classification(
    description: str,
    material: str,
    extra: dict,
    cache: CacheStore,
    physics_reference: dict,
) -> None:
    """Validate boolean/enum classification fields."""
    if not extra:
        pytest.skip("no classification checks for this case")

    bp = await _get_blueprint(description, cache)

    for field, expected in extra.items():
        actual = _get_nested(bp, field)
        assert actual == expected, (
            f"{description}: {field}={actual!r}, expected {expected!r}"
        )
