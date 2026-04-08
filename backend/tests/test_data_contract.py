"""Data contract tests for the eval system's dependencies.

Deterministic — no LLM calls. Runs in `make test`.
Tests fixture schema validity, state mapping completeness, model roundtrips,
and CacheStore operations that eval tests depend on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.cache.scene import CreatureBehavior, PairwiseResult
from app.cache.store import CacheStore, normalize_name, pair_key
from app.models.blueprint import (
    Destructibility,
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.models.state import State, decode_state_change

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "evals" / "fixtures"

# Build state string mapping (same logic as evals/conftest.py)
STATE_STRING_TO_CODE: dict[str, int] = {}
for _s in State:
    STATE_STRING_TO_CODE[_s.name.lower()] = _s.value
    STATE_STRING_TO_CODE[f"remove_{_s.name.lower()}"] = _s.value + 7


# ---------------------------------------------------------------------------
# Fixture schema validation
# ---------------------------------------------------------------------------


class TestFixtureSchemas:
    """Verify YAML fixtures are well-formed and parseable."""

    def test_interaction_pairs_schema(self) -> None:
        with open(FIXTURES_DIR / "interaction_pairs.yaml") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert "pair" in entry, f"missing 'pair' in {entry}"
            assert isinstance(entry["pair"], list) and len(entry["pair"]) == 2
            assert "expected" in entry, f"missing 'expected' in {entry}"
            assert isinstance(entry["expected"], dict)
            assert "note" in entry, f"missing 'note' in {entry}"

    def test_creature_behaviors_schema(self) -> None:
        with open(FIXTURES_DIR / "creature_behaviors.yaml") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, list)
        assert len(data) > 0
        for entry in data:
            assert "creature" in entry, f"missing 'creature' in {entry}"
            assert "target" in entry, f"missing 'target' in {entry}"
            assert "expected" in entry, f"missing 'expected' in {entry}"
            assert isinstance(entry["expected"], dict)
            assert "note" in entry, f"missing 'note' in {entry}"

    def test_physics_reference_schema(self) -> None:
        with open(FIXTURES_DIR / "physics_reference.yaml") as f:
            data = yaml.safe_load(f)
        assert isinstance(data, dict)
        assert len(data) > 0
        for material, props in data.items():
            for field in ("mass", "friction", "bounce", "gravity"):
                assert field in props, f"{material} missing '{field}'"
                assert isinstance(props[field], list) and len(props[field]) == 2, (
                    f"{material}.{field} must be a 2-element list"
                )


# ---------------------------------------------------------------------------
# State string mapping completeness
# ---------------------------------------------------------------------------


class TestStateMapping:
    """Every state string used in fixture files maps to a valid code."""

    def test_all_fixture_states_map(self) -> None:
        with open(FIXTURES_DIR / "interaction_pairs.yaml") as f:
            data = yaml.safe_load(f)
        for entry in data:
            expected = entry["expected"]
            for key in ("state_a", "state_b"):
                if key in expected:
                    state_str = expected[key]
                    assert state_str in STATE_STRING_TO_CODE, (
                        f"unmapped state string: {state_str!r} in {entry['pair']}"
                    )
                    code = STATE_STRING_TO_CODE[state_str]
                    assert 1 <= code <= 14, f"code {code} out of range for {state_str}"

    def test_all_creature_movement_values_valid(self) -> None:
        with open(FIXTURES_DIR / "creature_behaviors.yaml") as f:
            data = yaml.safe_load(f)
        for entry in data:
            exp = entry["expected"]
            if "movement" in exp:
                assert 0 <= exp["movement"] <= 3, (
                    f"invalid movement {exp['movement']} for {entry['creature']}"
                )
            if "action" in exp:
                assert 0 <= exp["action"] <= 6, (
                    f"invalid action {exp['action']} for {entry['creature']}"
                )

    def test_state_string_to_code_covers_all_states(self) -> None:
        """Mapping includes add + remove for all 7 states."""
        for s in State:
            assert s.name.lower() in STATE_STRING_TO_CODE
            assert f"remove_{s.name.lower()}" in STATE_STRING_TO_CODE
        assert len(STATE_STRING_TO_CODE) == 14


# ---------------------------------------------------------------------------
# decode_state_change exhaustive sweep
# ---------------------------------------------------------------------------


class TestDecodeStateChange:
    def test_zero_returns_none(self) -> None:
        assert decode_state_change(0) is None

    @pytest.mark.parametrize("code", range(1, 8))
    def test_add_states(self, code: int) -> None:
        result = decode_state_change(code)
        assert result is not None
        action, state = result
        assert action == "add"
        assert state == State(code)

    @pytest.mark.parametrize("code", range(8, 15))
    def test_remove_states(self, code: int) -> None:
        result = decode_state_change(code)
        assert result is not None
        action, state = result
        assert action == "remove"
        assert state == State(code - 7)

    @pytest.mark.parametrize("code", [-1, 15, 100, -100])
    def test_invalid_returns_none(self, code: int) -> None:
        assert decode_state_change(code) is None


# ---------------------------------------------------------------------------
# normalize_name + pair_key properties
# ---------------------------------------------------------------------------


class TestNameNormalization:
    def test_idempotent(self) -> None:
        for name in ["Fire Sword", "  big  boulder  ", "ROCK"]:
            assert normalize_name(normalize_name(name)) == normalize_name(name)

    def test_pair_key_symmetric(self) -> None:
        for a, b in [("fire", "wood"), ("Z", "A"), ("big rock", "tiny pebble")]:
            assert pair_key(a, b) == pair_key(b, a)

    def test_pair_key_deterministic(self) -> None:
        key1 = pair_key("fire sword", "wooden shield")
        key2 = pair_key("fire sword", "wooden shield")
        assert key1 == key2

    def test_pair_key_same_name(self) -> None:
        result = pair_key("rock", "rock")
        assert result == "rock::rock"


# ---------------------------------------------------------------------------
# Model roundtrips
# ---------------------------------------------------------------------------


class TestModelRoundtrips:
    def test_pairwise_result_roundtrip(self) -> None:
        pr = PairwiseResult(10, 20, 1, 8, 30, 0, False, True, True)
        d = pr.to_dict()
        pr2 = PairwiseResult.from_dict(d)
        assert pr == pr2

    def test_pairwise_result_defaults(self) -> None:
        pr = PairwiseResult.from_dict({})
        assert pr.damage_a == 0
        assert pr.damage_b == 0
        assert pr.state_change_a == 0
        assert pr.destroy_a is False
        assert pr.continuous is False

    def test_pairwise_result_extra_keys_ignored(self) -> None:
        pr = PairwiseResult.from_dict({"damage_a": 50, "bogus_key": 999})
        assert pr.damage_a == 50

    def test_creature_behavior_roundtrip(self) -> None:
        cb = CreatureBehavior(movement=0, strength=90, action=5, param=0)
        d = cb.to_dict()
        cb2 = CreatureBehavior.from_dict(d)
        assert cb == cb2

    def test_creature_behavior_defaults(self) -> None:
        cb = CreatureBehavior.from_dict({})
        assert cb.movement == 3  # ignore
        assert cb.strength == 0
        assert cb.action == 0
        assert cb.param == 0

    def test_blueprint_roundtrip(self) -> None:
        bp = GameObjectBlueprint(
            id="test-1",
            name="fire sword",
            description="a burning sword",
            visual_description="a flaming blade",
            physics=PhysicsProperties(
                mass_kg=2.0, height_cm=90, friction=35, bounce=15, gravity=60,
            ),
            destructibility=Destructibility(armor=40, hp=60, indestructible=False),
            affordance=0,
            autonomous=False,
            has_field=True,
            field_range_cm=100,
            destruction_result_name="broken sword",
        )
        d = bp.model_dump()
        bp2 = GameObjectBlueprint.model_validate(d)
        assert bp2.name == bp.name
        assert bp2.physics.mass_kg == bp.physics.mass_kg
        assert bp2.destructibility.armor == bp.destructibility.armor
        assert bp2.has_field == bp.has_field
        assert bp2.field_range_cm == bp.field_range_cm


# ---------------------------------------------------------------------------
# CacheStore async operations
# ---------------------------------------------------------------------------


@pytest.fixture
async def memory_cache(tmp_path):
    store = await CacheStore.open(str(tmp_path / "test.db"))
    yield store
    await store.close()


async def test_cache_creation_roundtrip(memory_cache: CacheStore) -> None:
    await memory_cache.put_creation("fire sword", {"mass_kg": 2.0, "gravity": 60})
    result = await memory_cache.get_creation("fire sword")
    assert result == {"mass_kg": 2.0, "gravity": 60}


async def test_cache_pairwise_roundtrip(memory_cache: CacheStore) -> None:
    value = {"damage_a": 0, "damage_b": 30, "state_change_b": 1}
    await memory_cache.put_pairwise("fire", "wood", value)
    result = await memory_cache.get_pairwise("fire", "wood")
    assert result == value
    # Order-invariant
    result2 = await memory_cache.get_pairwise("wood", "fire")
    assert result2 == value


async def test_cache_miss_returns_none(memory_cache: CacheStore) -> None:
    assert await memory_cache.get_creation("nonexistent") is None
    assert await memory_cache.get_pairwise("a", "b") is None
