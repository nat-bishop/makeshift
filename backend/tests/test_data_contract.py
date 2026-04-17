"""Data contract tests for the eval system's dependencies.

Deterministic — no LLM calls. Runs in `make test`.
Tests fixture schema validity, state mapping completeness, model roundtrips,
and CacheStore operations that eval tests depend on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from app.cache.scene import BehaviorEntry
from app.cache.store import CacheStore, normalize_name, pair_key
from app.models.blueprint import (
    GameObjectBlueprint,
    PhysicsProperties,
)
from app.models.state import State, decode_state_change

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "evals" / "fixtures"

# Build state string mapping (same logic as evals/conftest.py)
STATE_STRING_TO_CODE: dict[str, int] = {}
for _s in State:
    STATE_STRING_TO_CODE[_s.name.lower()] = _s.value
    STATE_STRING_TO_CODE[f"remove_{_s.name.lower()}"] = _s.value + len(State)


# ---------------------------------------------------------------------------
# Fixture schema validation
# ---------------------------------------------------------------------------


class TestFixtureSchemas:
    """Verify unified eval_suite.yaml is well-formed and parseable."""

    def test_eval_suite_archetypes(self) -> None:
        with open(FIXTURES_DIR / "eval_suite.yaml") as f:
            data = yaml.safe_load(f)
        archetypes = data["archetypes"]
        assert isinstance(archetypes, dict)
        assert len(archetypes) > 0
        for name, arch in archetypes.items():
            assert isinstance(arch, dict), f"{name} archetype is not a dict"

    def test_eval_suite_behaviors(self) -> None:
        with open(FIXTURES_DIR / "eval_suite.yaml") as f:
            data = yaml.safe_load(f)
        behaviors = data["behaviors"]
        assert isinstance(behaviors, list)
        assert len(behaviors) > 0
        for entry in behaviors:
            assert "subject" in entry, f"missing 'subject' in {entry}"
            assert "targets" in entry, f"missing 'targets' in {entry}"
            for t in entry["targets"]:
                assert "name" in t
                assert "expected" in t

    def test_eval_suite_creation_tests_have_expected(self) -> None:
        with open(FIXTURES_DIR / "eval_suite.yaml") as f:
            data = yaml.safe_load(f)
        for entry in data["creation_tests"]:
            assert "name" in entry, f"creation_test missing 'name': {entry}"
            assert "expected" in entry, f"creation_test '{entry['name']}' has no expected values"


# ---------------------------------------------------------------------------
# State string mapping completeness
# ---------------------------------------------------------------------------


class TestStateMapping:
    """Every state string used in fixture files maps to a valid code."""

    def test_all_behavior_values_valid(self) -> None:
        with open(FIXTURES_DIR / "eval_suite.yaml") as f:
            data = yaml.safe_load(f)
        for entry in data["behaviors"]:
            for t in entry["targets"]:
                exp = t["expected"]
                if "movement" in exp:
                    mv = exp["movement"]
                    vals = mv if isinstance(mv, list) else [mv]
                    for v in vals:
                        assert 0 <= v <= 2, (
                            f"invalid movement {v} for {entry['subject']} vs {t['name']}"
                        )
                if "action" in exp:
                    vals = exp["action"] if isinstance(exp["action"], list) else [exp["action"]]
                    for v in vals:
                        assert 0 <= v <= 4, (
                            f"invalid action {v} for {entry['subject']} vs {t['name']}"
                        )
                if "state_action" in exp:
                    vals = (
                        exp["state_action"]
                        if isinstance(exp["state_action"], list)
                        else [exp["state_action"]]
                    )
                    for v in vals:
                        assert 0 <= v <= 2, (
                            f"invalid state_action {v} for {entry['subject']} vs {t['name']}"
                        )
                if "delivery" in exp:
                    vals = (
                        exp["delivery"] if isinstance(exp["delivery"], list) else [exp["delivery"]]
                    )
                    for v in vals:
                        assert 0 <= v <= 1, (
                            f"invalid delivery {v} for {entry['subject']} vs {t['name']}"
                        )

    def test_state_string_to_code_covers_all_states(self) -> None:
        """Mapping includes add + remove for all 4 states."""
        for s in State:
            assert s.name.lower() in STATE_STRING_TO_CODE
            assert f"remove_{s.name.lower()}" in STATE_STRING_TO_CODE
        assert len(STATE_STRING_TO_CODE) == 8


# ---------------------------------------------------------------------------
# decode_state_change exhaustive sweep
# ---------------------------------------------------------------------------


class TestDecodeStateChange:
    def test_zero_returns_none(self) -> None:
        assert decode_state_change(0) is None

    @pytest.mark.parametrize("code", range(1, 5))
    def test_add_states(self, code: int) -> None:
        result = decode_state_change(code)
        assert result is not None
        action, state = result
        assert action == "add"
        assert state == State(code)

    @pytest.mark.parametrize("code", range(5, 9))
    def test_remove_states(self, code: int) -> None:
        result = decode_state_change(code)
        assert result is not None
        action, state = result
        assert action == "remove"
        assert state == State(code - 4)

    @pytest.mark.parametrize("code", [-1, 9, 100, -100])
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
    def test_behavior_entry_roundtrip(self) -> None:
        be = BehaviorEntry(
            movement=0,
            priority=3,
            action=1,
            amount=50,
            state_action=1,
            state_id=2,
            delivery=1,
            projectile_name="missile",
        )
        d = be.to_dict()
        be2 = BehaviorEntry.from_dict(d)
        assert be == be2

    def test_behavior_entry_defaults(self) -> None:
        be = BehaviorEntry.from_dict({})
        assert be.movement == 2  # ignore
        assert be.priority == 0
        assert be.action == 0
        assert be.amount == 0
        assert be.state_action == 0
        assert be.state_id == 0
        assert be.delivery == 0
        assert be.projectile_name == ""

    def test_behavior_entry_extra_keys_ignored(self) -> None:
        be = BehaviorEntry.from_dict({"movement": 1, "priority": 2, "bogus_key": 999})
        assert be.movement == 1
        assert be.priority == 2

    def test_blueprint_roundtrip(self) -> None:
        bp = GameObjectBlueprint(
            id="test-1",
            name="fire sword",
            description="a burning sword",
            visual_description="a flaming blade",
            physics=PhysicsProperties(
                mass_kg=2.0,
                height_cm=90,
                surface=1,
                bounce=15,
                gravity=60,
            ),
            durability=3,
            affordance=0,
            active=False,
            speed=2,
            initial_states=[1],
            susceptible_states=[1, 3],
            destruction_result_name="broken sword",
        )
        d = bp.model_dump()
        bp2 = GameObjectBlueprint.model_validate(d)
        assert bp2.name == bp.name
        assert bp2.physics.mass_kg == bp.physics.mass_kg
        assert bp2.durability == bp.durability
        assert bp2.speed == bp.speed
        assert bp2.initial_states == [1]
        assert bp2.susceptible_states == [1, 3]

    def test_blueprint_missing_speed_defaults(self) -> None:
        """Old cached blueprints without speed field should default to 2 (normal)."""
        d = {
            "id": "test-2",
            "name": "rock",
            "description": "a rock",
            "visual_description": "a grey rock",
            "physics": {"mass_kg": 5.0, "height_cm": 20, "surface": 1, "bounce": 10, "gravity": 60},
            "durability": 4,
            "affordance": 3,
            "active": False,
        }
        bp = GameObjectBlueprint.model_validate(d)
        assert bp.speed == 2


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


async def test_cache_miss_returns_none(memory_cache: CacheStore) -> None:
    assert await memory_cache.get_creation("nonexistent") is None
