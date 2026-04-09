"""Tests for V3 cache system (store + scene)."""

import pytest
from app.cache.scene import CreatureBehavior, PairwiseResult, SceneCache, nothing_happens
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


async def test_pairwise_cache_roundtrip(cache):
    value = {"damage_a": 0, "damage_b": 40, "state_change_b": 1}
    await cache.put_pairwise("fire sword", "wooden shield", value)
    result = await cache.get_pairwise("fire sword", "wooden shield")
    assert result == value


async def test_pairwise_cache_order_invariant(cache):
    value = {"damage_b": 30}
    await cache.put_pairwise("wooden shield", "fire sword", value)
    result = await cache.get_pairwise("fire sword", "wooden shield")
    assert result == value


async def test_exists_creation(cache):
    assert not await cache.exists_creation("fire sword")
    await cache.put_creation("fire sword", {"mass_kg": 1.5})
    assert await cache.exists_creation("fire sword")
    assert await cache.exists_creation("  FIRE  SWORD  ")
    assert not await cache.exists_creation("ice sword")


async def test_exists_pairwise(cache):
    assert not await cache.exists_pairwise("fire sword", "wood")
    await cache.put_pairwise("fire sword", "wood", {"damage_b": 10})
    assert await cache.exists_pairwise("fire sword", "wood")
    assert await cache.exists_pairwise("wood", "fire sword")


async def test_get_all_for_names_empty(cache):
    result = await cache.get_all_for_names("pairwise", [])
    assert result == {}


async def test_get_all_for_names_full(cache):
    await cache.put_pairwise("sword", "shield", {"d": 1})
    await cache.put_pairwise("sword", "rock", {"d": 2})
    await cache.put_pairwise("shield", "rock", {"d": 3})
    result = await cache.get_all_for_names("pairwise", ["sword", "shield", "rock"])
    assert len(result) == 3
    assert result[pair_key("sword", "shield")] == {"d": 1}


async def test_get_all_for_names_partial(cache):
    await cache.put_pairwise("sword", "shield", {"d": 1})
    result = await cache.get_all_for_names("pairwise", ["sword", "shield", "rock"])
    assert len(result) == 1


async def test_pairwise_invalidation(cache):
    await cache.put_pairwise("fire sword", "wooden shield", {"d": 1})
    await cache.put_pairwise("fire sword", "rock", {"d": 2})
    await cache.put_pairwise("rock", "wooden shield", {"d": 3})

    count = await cache.invalidate_pairwise("fire sword")
    assert count == 2

    assert await cache.get_pairwise("fire sword", "wooden shield") is None
    assert await cache.get_pairwise("fire sword", "rock") is None
    assert await cache.get_pairwise("rock", "wooden shield") is not None


# --- SceneCache ---


class TestSceneCache:
    def test_pairwise_put_get(self):
        sc = SceneCache()
        pr = PairwiseResult(10, 20, 1, 0, 30, False)
        sc.put_pairwise("fire sword", "wood", pr)
        assert sc.get_pairwise("fire sword", "wood") is pr

    def test_pairwise_order_invariant(self):
        sc = SceneCache()
        pr = PairwiseResult(0, 0, 0, 0, 0, False)
        sc.put_pairwise("b", "a", pr)
        assert sc.get_pairwise("a", "b") is pr

    def test_stale_returns_none(self):
        sc = SceneCache()
        pr = PairwiseResult(5, 5, 0, 0, 0, False)
        sc.put_pairwise("x", "y", pr)
        sc.mark_stale("x")
        assert sc.get_pairwise("x", "y") is None

    def test_put_clears_stale(self):
        sc = SceneCache()
        pr = PairwiseResult(5, 5, 0, 0, 0, False)
        sc.put_pairwise("x", "y", pr)
        sc.mark_stale("x")
        pr2 = PairwiseResult(10, 10, 0, 0, 0, False)
        sc.put_pairwise("x", "y", pr2)
        assert sc.get_pairwise("x", "y") is pr2

    def test_creature_behavior(self):
        sc = SceneCache()
        cb = CreatureBehavior(movement=0, priority=3, action=5, amount=0, state_id=0)
        sc.put_creature("zombie", "brain", cb)
        assert sc.get_creature("zombie", "brain") is cb
        assert sc.get_creature("zombie", "rock") is None

    def test_nothing_happens(self):
        pr = nothing_happens()
        assert pr.damage_a == 0
        assert pr.damage_b == 0
        assert not pr.continuous
        assert pr.force_b == 0

    def test_mark_creature_stale_for_target(self):
        sc = SceneCache()
        sc.put_creature("zombie", "sword", CreatureBehavior(0, 3, 1, 20, 0))
        sc.put_creature("zombie", "rock", CreatureBehavior(2, 2, 0, 0, 0))
        sc.put_creature("cat", "sword", CreatureBehavior(1, 3, 0, 0, 0))
        # Mark sword stale — zombie->sword and cat->sword should be removed
        removed = sc.mark_creature_stale_for_target("sword")
        assert len(removed) == 2
        assert sc.get_creature("zombie", "sword") is None
        assert sc.get_creature("cat", "sword") is None
        assert sc.get_creature("zombie", "rock") is not None

    def test_mark_creature_stale_for_creature(self):
        sc = SceneCache()
        sc.put_creature("zombie", "sword", CreatureBehavior(0, 3, 1, 20, 0))
        sc.put_creature("zombie", "rock", CreatureBehavior(2, 2, 0, 0, 0))
        sc.put_creature("cat", "sword", CreatureBehavior(1, 3, 0, 0, 0))
        # Mark zombie stale — zombie->sword and zombie->rock should be removed
        removed = sc.mark_creature_stale_for_creature("zombie")
        assert len(removed) == 2
        assert sc.get_creature("zombie", "sword") is None
        assert sc.get_creature("zombie", "rock") is None
        assert sc.get_creature("cat", "sword") is not None

    def test_all_pairwise_for(self):
        sc = SceneCache()
        sc.put_pairwise(
            "fire sword",
            "wood",
            PairwiseResult(10, 20, 0, 0, 0, False),
        )
        sc.put_pairwise("fire sword", "rock", PairwiseResult(0, 5, 0, 0, 0, False))
        sc.put_pairwise("rock", "wood", PairwiseResult(0, 0, 0, 0, 0, False))
        results = sc.all_pairwise_for("fire sword")
        assert len(results) == 2
