"""LLM quality gate: run creation pipeline against known objects, validate physics.

This test costs real LLM calls. Not in `make test`. Run manually:
    cd backend && uv run pytest tests/test_llm_quality_gate.py -v -s
"""

import pytest

from app.cache.manager import CacheManager
from app.creator.pipeline import create_object

EXPECTATIONS = [
    # (name, field, min, max, description)
    ("sword", "mass_kg", 0.5, 5.0, "sword should weigh 0.5-5kg"),
    ("sword", "gravity", 40, 65, "sword has normal gravity"),
    ("sword", "affordance", 0, 0, "sword is carryable"),
    ("sword", "autonomous", False, False, "sword is not alive"),
    ("balloon", "gravity", 0, 25, "balloon floats"),
    ("balloon", "mass_kg", 0.001, 0.5, "balloon is very light"),
    ("rock", "mass_kg", 1.0, 100, "rock weighs 1-100kg"),
    ("rock", "bounce", 0, 20, "rock doesn't bounce"),
    ("rubber ball", "bounce", 50, 100, "rubber ball bounces a lot"),
    ("ice cube", "friction", 0, 20, "ice is slippery"),
    ("campfire", "has_field", True, True, "campfire affects nearby things"),
    ("campfire", "gravity", 0, 30, "fire/smoke rises"),
    ("zombie", "autonomous", True, True, "zombie is alive"),
    ("cat", "autonomous", True, True, "cat is alive"),
    ("horse", "affordance", 1, 1, "horse is mountable"),
    ("ladder", "affordance", 2, 2, "ladder is climbable"),
    ("mountain", "indestructible", True, True, "mountain can't be destroyed"),
    ("glass bottle", "armor", 0, 25, "glass is fragile"),
    ("steel shield", "armor", 60, 100, "steel is resistant"),
]


@pytest.fixture
async def cache(tmp_path):
    import aiosqlite

    db = await aiosqlite.connect(str(tmp_path / "test_cache.db"))
    await db.execute(
        """CREATE TABLE cache (
        cache_type TEXT NOT NULL, cache_key TEXT NOT NULL,
        value_json TEXT NOT NULL, model_version TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (cache_type, cache_key))"""
    )
    cm = CacheManager(db)
    yield cm
    await db.close()


@pytest.mark.parametrize("name,field,min_val,max_val,desc", EXPECTATIONS)
async def test_physics_reasonable(cache, name, field, min_val, max_val, desc):
    bp = await create_object(name, cache)
    val = getattr(bp, field)
    if isinstance(min_val, bool):
        assert val == min_val, f"{desc}: got {val}"
    else:
        assert min_val <= val <= max_val, f"{desc}: {field}={val}, expected [{min_val}, {max_val}]"
