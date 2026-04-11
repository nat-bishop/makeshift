"""Tests for cache system (store + scene)."""

import pytest
from app.cache.scene import BehaviorCache, BehaviorEntry, CollisionRule, no_force
from app.cache.store import CacheStore, normalize_name, pair_key

# --- Key normalization ---


class TestKeyNormalization:
    def test_normalize_name(self):
        assert normalize_name("  FIRE  SWORD ") == "fire sword"
        assert normalize_name("Rock") == "rock"
        assert normalize_name("  a  ") == "a"

    def test_pair_key_sorts(self):
        assert pair_key("wooden shield", "fire sword") == "fire sword::wooden shield"
        assert pair_key("fire sword", "wooden shield") == "fire sword::wooden shield"
        assert pair_key("a", "b") == "a::b"
        assert pair_key("b", "a") == "a::b"

    def test_pair_key_normalizes(self):
        assert pair_key("Fire Sword", "  WOODEN  SHIELD  ") == "fire sword::wooden shield"


# --- CacheStore ---


@pytest.fixture
async def cache(tmp_path):
    path = str(tmp_path / "test_cache.db")
    store = await CacheStore.open(path)
    yield store
    await store.close()


async def test_creation_cache_roundtrip(cache):
    await cache.put_creation("fire sword", {"mass_kg": 1.5, "gravity": 50})
    result = await cache.get_creation("fire sword")
    assert result == {"mass_kg": 1.5, "gravity": 50}


async def test_creation_cache_normalized(cache):
    await cache.put_creation("  FIRE SWORD  ", {"mass_kg": 1.5})
    result = await cache.get_creation("fire sword")
    assert result is not None
    assert result["mass_kg"] == 1.5


async def test_creation_cache_miss(cache):
    result = await cache.get_creation("nonexistent")
    assert result is None


async def test_collision_cache_roundtrip(cache):
    value = {"force_on_b": 30}
    await cache.put_collision("fire sword", "wooden shield", value)
    result = await cache.get_collision("fire sword", "wooden shield")
    assert result == value


async def test_collision_cache_order_invariant(cache):
    value = {"force_on_b": -80}
    await cache.put_collision("wooden shield", "fire sword", value)
    result = await cache.get_collision("fire sword", "wooden shield")
    assert result == value


async def test_exists_creation(cache):
    assert not await cache.exists_creation("fire sword")
    await cache.put_creation("fire sword", {"mass_kg": 1.5})
    assert await cache.exists_creation("fire sword")
    assert await cache.exists_creation("  FIRE  SWORD  ")
    assert not await cache.exists_creation("ice sword")


async def test_get_all_collisions_empty(cache):
    result = await cache.get_all_collisions_for_names([])
    assert result == {}


async def test_get_all_collisions_full(cache):
    await cache.put_collision("sword", "shield", {"force_on_b": 30})
    await cache.put_collision("sword", "rock", {"force_on_b": 0})
    await cache.put_collision("shield", "rock", {"force_on_b": -30})
    result = await cache.get_all_collisions_for_names(["sword", "shield", "rock"])
    assert len(result) == 3
    assert result[pair_key("sword", "shield")] == {"force_on_b": 30}


async def test_get_all_collisions_partial(cache):
    await cache.put_collision("sword", "shield", {"force_on_b": 30})
    result = await cache.get_all_collisions_for_names(["sword", "shield", "rock"])
    assert len(result) == 1


# --- BehaviorCache ---


class TestBehaviorCache:
    def test_collision_put_get(self):
        bc = BehaviorCache()
        rule = CollisionRule(force_on_b=30)
        bc.put_collision("fire sword", "wood", rule)
        assert bc.get_collision("fire sword", "wood") is rule

    def test_collision_order_invariant(self):
        bc = BehaviorCache()
        rule = CollisionRule(force_on_b=0)
        bc.put_collision("b", "a", rule)
        assert bc.get_collision("a", "b") is rule

    def test_behavior_put_get(self):
        bc = BehaviorCache()
        entry = BehaviorEntry(movement=0, priority=3, action=5, amount=0, state_id=0)
        bc.put_behavior("zombie", "brain", entry)
        assert bc.get_behavior("zombie", "brain") is entry
        assert bc.get_behavior("zombie", "rock") is None

    def test_invalidate_behavior(self):
        bc = BehaviorCache()
        bc.put_behavior("zombie", "sword", BehaviorEntry(0, 3, 1, 20, 0))
        bc.put_behavior("zombie", "rock", BehaviorEntry(2, 2, 0, 0, 0))
        bc.put_behavior("cat", "sword", BehaviorEntry(1, 3, 0, 0, 0))
        removed = bc.invalidate_behavior("sword")
        assert len(removed) == 2
        assert bc.get_behavior("zombie", "sword") is None
        assert bc.get_behavior("cat", "sword") is None
        assert bc.get_behavior("zombie", "rock") is not None

    def test_no_force(self):
        rule = no_force()
        assert rule.force_on_b == 0

    def test_collision_rule_to_dict(self):
        rule = CollisionRule(force_on_b=30)
        assert rule.to_dict() == {"force_on_b": 30}

    def test_collision_rule_from_dict(self):
        rule = CollisionRule.from_dict({"force_on_b": -80})
        assert rule.force_on_b == -80

    def test_behavior_entry_to_dict(self):
        entry = BehaviorEntry(movement=0, priority=3, action=1, amount=50, state_id=0)
        d = entry.to_dict()
        assert d["movement"] == 0
        assert d["priority"] == 3
        assert d["action"] == 1
        assert d["amount"] == 50

    def test_behavior_entry_from_dict(self):
        entry = BehaviorEntry.from_dict({"movement": 1, "priority": 2})
        assert entry.movement == 1
        assert entry.priority == 2
        assert entry.action == 0  # default
