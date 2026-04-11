"""Tests for cache system (store + scene)."""

import pytest
from app.cache.scene import BehaviorCache, BehaviorEntry
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


async def test_exists_creation(cache):
    assert not await cache.exists_creation("fire sword")
    await cache.put_creation("fire sword", {"mass_kg": 1.5})
    assert await cache.exists_creation("fire sword")
    assert await cache.exists_creation("  FIRE  SWORD  ")
    assert not await cache.exists_creation("ice sword")


# --- BehaviorCache ---


class TestBehaviorCache:
    def test_behavior_put_get(self):
        bc = BehaviorCache()
        entry = BehaviorEntry(movement=0, priority=3, action=4, amount=0, state_id=0)
        bc.put_behavior("zombie", "brain", entry)
        assert bc.get_behavior("zombie", "brain") is entry
        assert bc.get_behavior("zombie", "rock") is None

    def test_invalidate_behavior(self):
        bc = BehaviorCache()
        bc.put_behavior("zombie", "sword", BehaviorEntry(0, 3, 1, 20))
        bc.put_behavior("zombie", "rock", BehaviorEntry(2, 2, 0, 0))
        bc.put_behavior("cat", "sword", BehaviorEntry(1, 3, 0, 0))
        removed = bc.invalidate_behavior("sword")
        assert len(removed) == 2
        assert bc.get_behavior("zombie", "sword") is None
        assert bc.get_behavior("cat", "sword") is None
        assert bc.get_behavior("zombie", "rock") is not None

    def test_behavior_entry_to_dict(self):
        entry = BehaviorEntry(
            movement=0,
            priority=3,
            action=1,
            amount=50,
            state_action=1,
            state_id=2,
            force=1,
        )
        d = entry.to_dict()
        assert d["movement"] == 0
        assert d["priority"] == 3
        assert d["action"] == 1
        assert d["amount"] == 50
        assert d["state_action"] == 1
        assert d["state_id"] == 2
        assert d["force"] == 1

    def test_behavior_entry_from_dict(self):
        entry = BehaviorEntry.from_dict({"movement": 1, "priority": 2})
        assert entry.movement == 1
        assert entry.priority == 2
        assert entry.action == 0  # default
        assert entry.state_action == 0  # default
        assert entry.force == 0  # default

    def test_behavior_entry_from_dict_full(self):
        entry = BehaviorEntry.from_dict(
            {
                "movement": 0,
                "priority": 3,
                "action": 4,
                "amount": 80,
                "state_action": 2,
                "state_id": 1,
                "force": 1,
            }
        )
        assert entry.movement == 0
        assert entry.priority == 3
        assert entry.action == 4
        assert entry.amount == 80
        assert entry.state_action == 2
        assert entry.state_id == 1
        assert entry.force == 1
