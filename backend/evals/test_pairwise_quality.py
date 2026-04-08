"""Pairwise quality gate: does evaluate_pair() produce sensible interactions?

Loads interaction_pairs.yaml, builds hand-crafted blueprints with realistic
physics (used by _obj_summary()), and validates LLM pairwise results against
expected damage ranges, state changes, forces, and destruction flags.

Run: make eval-pairwise
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.cache.scene import SceneCache
from app.cache.store import CacheStore, normalize_name
from app.engine.pairwise import evaluate_pair

from evals.helpers import PUSH_PULL_MAP, STATE_STRING_TO_CODE, make_blueprint, orient_expected

# ---------------------------------------------------------------------------
# Archetype physics for hand-built blueprints.
# _obj_summary() reads: mass_kg, armor, has_field, field_range_cm, autonomous, indestructible
# ---------------------------------------------------------------------------

ARCHETYPES: dict[str, dict] = {
    # Fire / Heat sources
    "fire": {
        "mass_kg": 0.1,
        "height_cm": 40,
        "friction": 5,
        "bounce": 5,
        "gravity": 10,
        "has_field": True,
        "field_range_cm": 100,
    },
    "campfire": {
        "mass_kg": 5.0,
        "height_cm": 60,
        "friction": 30,
        "bounce": 5,
        "gravity": 55,
        "has_field": True,
        "field_range_cm": 150,
    },
    "lava": {
        "mass_kg": 10.0,
        "height_cm": 20,
        "friction": 30,
        "bounce": 5,
        "gravity": 60,
        "has_field": True,
        "field_range_cm": 120,
    },
    # Solids / Materials
    "wood": {"mass_kg": 3.0, "height_cm": 50, "friction": 50, "bounce": 15, "gravity": 55},
    "ice": {"mass_kg": 2.0, "height_cm": 30, "friction": 5, "bounce": 20, "gravity": 52},
    "ice cube": {"mass_kg": 0.3, "height_cm": 8, "friction": 5, "bounce": 20, "gravity": 50},
    "glass bottle": {
        "mass_kg": 0.4,
        "height_cm": 25,
        "friction": 20,
        "bounce": 10,
        "gravity": 55,
        "armor": 10,
    },
    "glass window": {
        "mass_kg": 2.0,
        "height_cm": 100,
        "friction": 15,
        "bounce": 10,
        "gravity": 55,
        "armor": 5,
    },
    "glass vase": {
        "mass_kg": 0.5,
        "height_cm": 30,
        "friction": 20,
        "bounce": 10,
        "gravity": 55,
        "armor": 8,
    },
    "stone wall": {
        "mass_kg": 200.0,
        "height_cm": 300,
        "friction": 50,
        "bounce": 5,
        "gravity": 70,
        "armor": 80,
        "indestructible": True,
    },
    "rock": {
        "mass_kg": 5.0,
        "height_cm": 20,
        "friction": 40,
        "bounce": 10,
        "gravity": 60,
        "armor": 60,
    },
    # Weapons / Tools
    "sword": {"mass_kg": 2.0, "height_cm": 90, "friction": 35, "bounce": 15, "gravity": 60},
    "iron sword": {"mass_kg": 2.0, "height_cm": 90, "friction": 35, "bounce": 15, "gravity": 60},
    "wooden sword": {"mass_kg": 1.0, "height_cm": 80, "friction": 45, "bounce": 15, "gravity": 55},
    "wooden shield": {
        "mass_kg": 2.0,
        "height_cm": 60,
        "friction": 45,
        "bounce": 15,
        "gravity": 55,
        "armor": 40,
    },
    "boulder": {
        "mass_kg": 100.0,
        "height_cm": 80,
        "friction": 40,
        "bounce": 5,
        "gravity": 70,
        "armor": 70,
    },
    # Explosives
    "dynamite": {"mass_kg": 0.5, "height_cm": 20, "friction": 40, "bounce": 10, "gravity": 55},
    "bomb": {"mass_kg": 3.0, "height_cm": 25, "friction": 35, "bounce": 10, "gravity": 60},
    # Electrical
    "lightning rod": {
        "mass_kg": 3.0,
        "height_cm": 150,
        "friction": 30,
        "bounce": 10,
        "gravity": 60,
        "has_field": True,
        "field_range_cm": 80,
    },
    "live wire": {
        "mass_kg": 0.5,
        "height_cm": 200,
        "friction": 20,
        "bounce": 5,
        "gravity": 55,
        "has_field": True,
        "field_range_cm": 50,
    },
    "lightning": {
        "mass_kg": 0.01,
        "height_cm": 500,
        "friction": 0,
        "bounce": 0,
        "gravity": 5,
        "has_field": True,
        "field_range_cm": 200,
    },
    # Liquids
    "water": {"mass_kg": 2.0, "height_cm": 10, "friction": 5, "bounce": 5, "gravity": 50},
    "water puddle": {"mass_kg": 1.0, "height_cm": 5, "friction": 5, "bounce": 5, "gravity": 50},
    # Acid
    "acid": {
        "mass_kg": 1.0,
        "height_cm": 10,
        "friction": 5,
        "bounce": 5,
        "gravity": 50,
        "has_field": True,
        "field_range_cm": 30,
    },
    # Wind
    "fan": {
        "mass_kg": 3.0,
        "height_cm": 40,
        "friction": 30,
        "bounce": 10,
        "gravity": 55,
        "has_field": True,
        "field_range_cm": 200,
    },
    "tornado": {
        "mass_kg": 0.1,
        "height_cm": 500,
        "friction": 0,
        "bounce": 0,
        "gravity": 10,
        "has_field": True,
        "field_range_cm": 300,
    },
    # Light objects
    "feather": {"mass_kg": 0.005, "height_cm": 15, "friction": 20, "bounce": 10, "gravity": 15},
    "smoke cloud": {"mass_kg": 0.01, "height_cm": 100, "friction": 0, "bounce": 0, "gravity": 5},
    # Magnetic
    "magnet": {
        "mass_kg": 1.0,
        "height_cm": 10,
        "friction": 30,
        "bounce": 10,
        "gravity": 55,
        "has_field": True,
        "field_range_cm": 100,
    },
    # Toxic
    "poison mushroom": {
        "mass_kg": 0.1,
        "height_cm": 10,
        "friction": 40,
        "bounce": 10,
        "gravity": 50,
        "has_field": True,
        "field_range_cm": 20,
    },
    # Living
    "person": {
        "mass_kg": 70.0,
        "height_cm": 175,
        "friction": 40,
        "bounce": 10,
        "gravity": 55,
        "autonomous": True,
    },
    "rabbit": {
        "mass_kg": 2.0,
        "height_cm": 25,
        "friction": 40,
        "bounce": 15,
        "gravity": 50,
        "autonomous": True,
    },
    # Reflective
    "mirror shield": {
        "mass_kg": 3.0,
        "height_cm": 60,
        "friction": 20,
        "bounce": 30,
        "gravity": 55,
        "armor": 50,
    },
    # Frozen
    "frozen statue": {
        "mass_kg": 50.0,
        "height_cm": 180,
        "friction": 10,
        "bounce": 5,
        "gravity": 65,
        "armor": 20,
    },
    # Sticky
    "tar pit": {
        "mass_kg": 100.0,
        "height_cm": 30,
        "friction": 90,
        "bounce": 0,
        "gravity": 60,
        "has_field": True,
        "field_range_cm": 100,
    },
}


def _get_archetype(name: str) -> dict:
    """Look up archetype by normalized name, fall back to defaults."""
    key = normalize_name(name)
    if key in ARCHETYPES:
        return ARCHETYPES[key]
    # Fallback: generic defaults
    return {"mass_kg": 1.0, "height_cm": 30, "friction": 50, "bounce": 10, "gravity": 50}


# ---------------------------------------------------------------------------
# Load fixture data at module level for parametrize
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "interaction_pairs.yaml"
with open(_FIXTURE_PATH) as _f:
    _PAIR_DATA: list[dict] = yaml.safe_load(_f)

_PAIR_IDS = [f"{d['pair'][0]} vs {d['pair'][1]}" for d in _PAIR_DATA]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _PAIR_DATA, ids=_PAIR_IDS)
async def test_pairwise_interaction(
    case: dict,
    cache: CacheStore,
    scene: SceneCache,
) -> None:
    """Validate a single pairwise interaction against fixture expectations."""
    pair = case["pair"]
    raw_expected = case["expected"]

    # Build blueprints from archetypes
    bp_a = make_blueprint(pair[0], **_get_archetype(pair[0]))
    bp_b = make_blueprint(pair[1], **_get_archetype(pair[1]))

    # Run pairwise evaluation (sorts A/B lexicographically internally)
    result = await evaluate_pair(bp_a, bp_b, cache, scene)

    # Orient expected fields to match the sorted pair order
    expected = orient_expected(pair, raw_expected)

    # --- Validate each expected field ---

    def assert_range(field: str, actual: int, lo: float, hi: float) -> None:
        margin = (hi - lo) * 0.3
        tol_lo = max(0, lo - margin)
        tol_hi = min(100, hi + margin)
        assert tol_lo <= actual <= tol_hi, (
            f"{pair}: {field}={actual} outside [{tol_lo:.0f}, {tol_hi:.0f}]"
        )

    # Damage ranges
    if "damage_a" in expected:
        val = expected["damage_a"]
        if isinstance(val, list):
            assert_range("damage_a", result.damage_a, val[0], val[1])
        else:
            assert result.damage_a == val

    if "damage_b" in expected:
        val = expected["damage_b"]
        if isinstance(val, list):
            assert_range("damage_b", result.damage_b, val[0], val[1])
        else:
            assert result.damage_b == val

    # State changes
    if "state_a" in expected:
        expected_code = STATE_STRING_TO_CODE[expected["state_a"]]
        assert result.state_change_a == expected_code, (
            f"{pair}: state_change_a={result.state_change_a}, expected {expected_code} "
            f"({expected['state_a']})"
        )

    if "state_b" in expected:
        expected_code = STATE_STRING_TO_CODE[expected["state_b"]]
        assert result.state_change_b == expected_code, (
            f"{pair}: state_change_b={result.state_change_b}, expected {expected_code} "
            f"({expected['state_b']})"
        )

    # Destruction flags
    if "destroy_a" in expected:
        assert result.destroy_a == expected["destroy_a"], (
            f"{pair}: destroy_a={result.destroy_a}, expected {expected['destroy_a']}"
        )

    if "destroy_b" in expected:
        assert result.destroy_b == expected["destroy_b"], (
            f"{pair}: destroy_b={result.destroy_b}, expected {expected['destroy_b']}"
        )

    # Force
    if "force_b" in expected:
        val = expected["force_b"]
        if isinstance(val, list):
            assert_range("force_b", result.force_b, val[0], val[1])
        else:
            assert result.force_b == val

    if "force_a" in expected:
        # force_a doesn't exist on PairwiseResult — only force_b
        # If fixture specifies force_a after swap, it becomes force_b
        # This case shouldn't arise given the fixture structure
        pass

    # Push/pull
    if "push_pull" in expected:
        expected_pp = PUSH_PULL_MAP[expected["push_pull"]]
        assert result.push_pull == expected_pp, (
            f"{pair}: push_pull={result.push_pull}, expected {expected_pp} "
            f"({expected['push_pull']})"
        )

    # Continuous
    if "continuous" in expected:
        assert result.continuous == expected["continuous"], (
            f"{pair}: continuous={result.continuous}, expected {expected['continuous']}"
        )
