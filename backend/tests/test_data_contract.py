"""Phase 1: data contract tests."""

from app.cache.manager import CacheManager
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.pairwise import PairwiseResult
from app.models.states import STATE_CONTRADICTIONS, State, decode_state_change


def test_blueprint_roundtrip():
    bp = GameObjectBlueprint(
        id="test",
        name="fire sword",
        description="fire sword",
        mass_kg=1.5,
        height_cm=120,
        friction=30,
        bounce=10,
        gravity=50,
        armor=80,
        hp=90,
        indestructible=False,
        has_field=True,
        field_range_cm=150,
        autonomous=False,
        affordance=0,
        visual_descriptor=VisualDescriptor(
            visual_description="a flaming sword", size_category="small"
        ),
        destruction_result_name="broken sword blade",
    )
    j = bp.model_dump_json()
    bp2 = GameObjectBlueprint.model_validate_json(j)
    assert bp2.mass_kg == 1.5
    assert bp2.states == []
    assert bp2.destruction_result_name == "broken sword blade"


def test_blueprint_empty_states():
    bp = GameObjectBlueprint(
        id="t",
        name="rock",
        description="rock",
        mass_kg=5.0,
        height_cm=30,
        friction=50,
        bounce=5,
        gravity=60,
        armor=70,
        hp=80,
        indestructible=False,
        visual_descriptor=VisualDescriptor(visual_description="a gray rock"),
    )
    assert bp.states == []
    assert bp.destruction_result_name == ""


def test_state_decode():
    assert decode_state_change(0) is None
    assert decode_state_change(1) == ("add", State.ON_FIRE)
    assert decode_state_change(7) == ("add", State.MOLTEN)
    assert decode_state_change(8) == ("remove", State.ON_FIRE)
    assert decode_state_change(14) == ("remove", State.MOLTEN)
    assert decode_state_change(15) is None


def test_state_contradictions():
    assert State.FROZEN in STATE_CONTRADICTIONS[State.ON_FIRE]
    assert State.WET in STATE_CONTRADICTIONS[State.ON_FIRE]
    assert State.ON_FIRE in STATE_CONTRADICTIONS[State.FROZEN]
    assert State.MOLTEN in STATE_CONTRADICTIONS[State.FROZEN]


def test_pairwise_roundtrip():
    pr = PairwiseResult(damage_a=0, damage_b=40, state_change_b=1, force_b=20)
    d = pr.model_dump()
    assert d["state_change_b"] == 1
    assert d["destroy_a"] is False
    pr2 = PairwiseResult(**d)
    assert pr2.damage_b == 40


def test_cache_key_normalization():
    assert CacheManager.normalize_key("  Fire  Sword ") == "fire sword"
    assert CacheManager.normalize_key("FIRE SWORD") == "fire sword"


def test_cache_pair_key_sorting():
    assert CacheManager.pair_key("wooden shield", "fire sword") == "fire sword::wooden shield"
    assert CacheManager.pair_key("Fire Sword", "wooden shield") == "fire sword::wooden shield"


async def test_cache_get_set(tmp_path):
    import aiosqlite

    db = await aiosqlite.connect(str(tmp_path / "test_cache.db"))
    await db.execute(
        """CREATE TABLE cache (
        cache_type TEXT NOT NULL, cache_key TEXT NOT NULL,
        value_json TEXT NOT NULL, model_version TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (cache_type, cache_key))"""
    )
    cache = CacheManager(db)
    assert await cache.get("creation", "fire sword") is None
    await cache.set("creation", "fire sword", {"mass_kg": 1.5})
    result = await cache.get("creation", "fire sword")
    assert result["mass_kg"] == 1.5
    assert await cache.exists("creation", "fire sword")
    await db.close()
