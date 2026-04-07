# V3 Implementation Plan

10 phases, strictly ordered. Each phase lists exact files to create/modify/delete, inline data shapes, and a validation step. A fresh agent can execute any phase without reading the other V3 design docs.

**Ground rules:**
- Game is non-functional on this branch — no incremental migration tax
- If a V2 file is >50% rewritten, delete and recreate it
- Environment bodies become named objects in the pairwise cache (migration.md Option A)
- Creature behavior is scene-local in-memory, not in persistent cache
- PydanticAI agents for all LLM calls, `asyncio.gather()` for fan-out
- No client-side rate limiting — SGLang handles batching internally

---

## Dependency graph

```
Phase 0 (extract reference data)
  └─ Phase 1 (delete V2 backend, archive docs)
       └─ Phase 2 (V3 data models)
            └─ Phase 3 (unified cache)
                 └─ Phase 4 (LLM question runner)
                      └─ Phase 5 (creation pipeline)
                           └─ Phase 6 (pairwise interaction system)
                                └─ Phase 7 (creature behavior)
                                     └─ Phase 8 (Godot client rewrite)
                                          └─ Phase 9 (eval system + tests + cleanup)
```

Phases 8 and 9 have internal parallelism (noted in each).

---

## Phase 0 — Extract V2 reference data

**Why:** V2's rules and substance profiles encode game-design knowledge needed for V3 eval fixtures. Extract before deleting.

### Files to create

**`backend/evals/fixtures/v2_interaction_pairs.yaml`**

Convert the ~56 rules from `backend/app/engine/rules_data.py` into pairwise eval fixtures. Each entry maps two concrete object descriptions to expected interaction outcomes. ~25-30 representative entries covering the most gameplay-significant rules.

```yaml
# Derived from V2 rule: heat_flammable_ignite
- pair: ["fire sword", "wooden shield"]
  expected:
    damage_b_min: 20
    damage_b_max: 60
    state_change_b: 1  # add on_fire
  notes: "Heat source ignites flammable wood"

# Derived from V2 rule: liquid_heat_extinguish
- pair: ["bucket of water", "campfire"]
  expected:
    state_change_b: 8  # remove on_fire
    destroy_a: true     # water consumed
  notes: "Water extinguishes fire"

# Derived from V2 rule: sharp_breakable_damage
- pair: ["sword", "glass bottle"]
  expected:
    damage_b_min: 15
    damage_b_max: 50
  notes: "Sharp object damages fragile target"

# Derived from V2 rule: electric_wet_amplify
- pair: ["electric eel", "wet sponge"]
  expected:
    damage_b_min: 20
    state_change_b: 4  # add electrified
  notes: "Electricity amplified by wetness"

# Derived from V2 rule: cold_liquid_freeze
- pair: ["ice wand", "puddle of water"]
  expected:
    state_change_b: 2  # add frozen
  notes: "Cold freezes liquid"

# Derived from V2 rule: acid_breakable_corrode
- pair: ["acid flask", "metal shield"]
  expected:
    damage_b_min: 10
    state_change_b: 6  # add corroded
  notes: "Acid corrodes metal"

# Derived from V2 rule: heavy_breakable_crush
- pair: ["boulder", "glass bottle"]
  expected:
    damage_b_min: 30
    destroy_b: true
  notes: "Heavy object crushes fragile target"

# ... ~20 more entries covering: fire spread, melting, explosion, magnetism,
#     wind push, toxic damage, reflective deflection, creature combat
```

**`backend/evals/fixtures/v2_physics_reference.yaml`**

Reference physics from `SUBSTANCE_PROFILES` in `backend/app/models/substances.py` for calibrating physics reasonableness checks.

```yaml
# Substance profiles for physics calibration
metal:
  mass: 8.0
  friction: 0.4
  bounce: 0.1
  state: solid
  notes: "Heavy, grippy, no bounce"

wood:
  mass: 2.0
  friction: 0.6
  bounce: 0.2
  state: solid
  notes: "Medium weight, grippy"

stone:
  mass: 5.0
  friction: 0.5
  bounce: 0.05
  state: solid
  notes: "Heavy, moderate grip, no bounce"

glass:
  mass: 2.5
  friction: 0.2
  bounce: 0.0
  state: solid
  notes: "Medium, slippery, fragile"

rubber:
  mass: 1.2
  friction: 0.9
  bounce: 0.9
  state: solid
  notes: "Light, very grippy, very bouncy"

water:
  mass: 1.0
  friction: 0.1
  bounce: 0.0
  state: liquid

fire:
  mass: 0.1
  friction: 0.0
  bounce: 0.0
  state: energy
  notes: "Near-weightless energy"

smoke:
  mass: 0.01
  friction: 0.0
  bounce: 0.0
  state: gas
  notes: "Lighter than fire, rises"

ice:
  mass: 0.9
  friction: 0.05
  bounce: 0.1
  state: solid
  notes: "Like water but solid, very slippery"

flesh:
  mass: 1.0
  friction: 0.6
  bounce: 0.1
  state: solid
  notes: "Creature material, medium everything"
```

**`backend/evals/fixtures/v2_creature_behaviors.yaml`**

Reference creature behaviors for creature behavior eval quality testing.

```yaml
- creature: zombie
  target: brain
  expected_movement: 0  # approach
  expected_action: 5    # destroy (eat)
  notes: "Classic zombie behavior"

- creature: firefighter
  target: burning tree
  expected_movement: 0  # approach
  expected_action: 4    # remove state (on_fire)

- creature: cat
  target: dog
  expected_movement: 1  # flee

- creature: cat
  target: ball of yarn
  expected_movement: 2  # orbit
  expected_action: 0    # nothing (watches)

- creature: guard dog
  target: player
  expected_movement: 2  # orbit (patrol)
  expected_action: 0    # nothing (guard)

- creature: zombie cop
  target: donut
  expected_movement: 0  # approach
  expected_action: 5    # destroy (eat)

- creature: vampire
  target: garlic
  expected_movement: 1  # flee

- creature: doctor
  target: injured person
  expected_movement: 0  # approach
  expected_action: 2    # heal

# ... ~10 more covering: wolf+rabbit, dragon+gold, thief+gold,
#     bee+flower, shark+fish, spider+fly
```

### Validation

Files parse as valid YAML. No code changes yet — purely data extraction.

```bash
cd backend && python -c "import yaml; yaml.safe_load(open('evals/fixtures/v2_interaction_pairs.yaml')); print('OK')"
cd backend && python -c "import yaml; yaml.safe_load(open('evals/fixtures/v2_physics_reference.yaml')); print('OK')"
cd backend && python -c "import yaml; yaml.safe_load(open('evals/fixtures/v2_creature_behaviors.yaml')); print('OK')"
```

---

## Phase 1 — Delete V2 backend code, archive docs

**Why:** Clean slate. Every file listed here is >50% replaced by V3 or has no V3 equivalent.

### Files to delete

| File | Reason |
|------|--------|
| `backend/app/models/tags.py` | 31-tag enum, categories, contradictions → replaced by 7 states |
| `backend/app/models/substances.py` | 16 substances, profiles, elements → replaced by LLM physics |
| `backend/app/models/effects.py` | V2 EffectType/Effect → replaced by pairwise outcome format |
| `backend/app/models/rules.py` | InteractionRule model → no static rules in V3 |
| `backend/app/models/tag_behaviors.py` | Implied behaviors → creature behavior is per-pair |
| `backend/app/models/blueprint.py` | CreatorOutput, GameObjectBlueprint → replaced by V3Blueprint |
| `backend/app/creator/agent.py` | Single PydanticAI agent → replaced by question graph |
| `backend/app/engine/resolver.py` | RuleResolver → replaced by cache lookup |
| `backend/app/engine/rules_data.py` | 56 rules → replaced by pairwise cache |
| `backend/app/engine/trait_deriver.py` | derive_traits, resolve_profile → deleted, no trait derivation |
| `backend/app/routers/rules.py` | /api/rules endpoint → no static rules in V3 |

### Files to delete (tests, V2-specific)

| File | Reason |
|------|--------|
| `backend/tests/test_tags.py` | Tests V2 tag enums, contradictions |
| `backend/tests/test_trait_deriver.py` | Tests derive_traits, resolve_profile, combat_profile |
| `backend/tests/test_rules.py` | Tests RuleResolver |
| `backend/tests/test_rules_coverage.py` | Tests structural validity of 56 rules |
| `backend/tests/test_blueprint.py` | Tests CreatorOutput validation (substance, element, tags) |

### Docs to archive

Move to `docs/archive/`:
- `docs/ARCHITECTURE.md` → `docs/archive/ARCHITECTURE.md`
- `docs/GAME_DESIGN.md` → `docs/archive/GAME_DESIGN.md`
- `docs/object-system-v2.md` → `docs/archive/object-system-v2.md`
- `docs/action-plan.md` → `docs/archive/action-plan.md`

### Files to stub (fix broken imports)

These files import deleted V2 modules. Stub them so `make lint` passes (no syntax errors). Full rewrites happen in later phases.

**`backend/app/main.py`** — Remove imports of: `rules` router, `_get_agent`, any V2 model imports. Comment out agent warmup and rules router registration. Keep image pipeline warmup, session DB init, WebSocket registration.

**`backend/app/routers/objects.py`** — Remove imports of: `create_object` (V2), `GameObjectBlueprint`, substance/tag models. Replace `create_object_endpoint` body with `raise NotImplementedError("V3 creation pipeline not yet implemented")`.

**`backend/app/routers/sessions.py`** — Remove imports of: `ALL_RULES`, `InteractionRule`, rules serialization. Remove `rules` field from response models. Remove `_RULES_JSON` pre-computation.

**`backend/app/sessions/manager.py`** — Remove import of `GameObjectBlueprint`. Replace with a placeholder `# V3Blueprint imported in Phase 2`.

**`backend/app/images/pipeline.py`** — Remove import of `GameObjectBlueprint`. The `generate_sprite` function signature temporarily accepts `Any` until Phase 5.

**`backend/app/cli.py`** — Remove imports of V2 creator. Replace `cmd_create` body with `print("V3 creation pipeline not yet implemented")`.

### Validation

```bash
make lint   # passes (no import errors)
# make test WILL fail — that's expected. No V2 tests, no V3 tests yet.
# make typecheck WILL fail — stubs use Any/NotImplementedError.
```

---

## Phase 2 — V3 data models

**Why:** Every subsequent phase depends on these types. No LLM calls, no cache, no HTTP — just Pydantic models.

### Files to create

**`backend/app/models/states.py`** — The 7 interaction-only states.

```python
from enum import IntEnum


class State(IntEnum):
    """Interaction-only states. Never set at creation — objects are born stateless."""
    ON_FIRE = 1
    FROZEN = 2
    WET = 3
    ELECTRIFIED = 4
    POISONED = 5
    CORRODED = 6
    MOLTEN = 7


# Engine-enforced: adding a state auto-removes its contradictions.
STATE_CONTRADICTIONS: dict[State, frozenset[State]] = {
    State.ON_FIRE: frozenset({State.FROZEN, State.WET}),
    State.FROZEN: frozenset({State.ON_FIRE, State.MOLTEN}),
    State.WET: frozenset({State.ON_FIRE}),
    State.MOLTEN: frozenset({State.FROZEN}),
}

# State names for display/logging.
STATE_NAMES: dict[State, str] = {
    State.ON_FIRE: "on_fire",
    State.FROZEN: "frozen",
    State.WET: "wet",
    State.ELECTRIFIED: "electrified",
    State.POISONED: "poisoned",
    State.CORRODED: "corroded",
    State.MOLTEN: "molten",
}


def decode_state_change(value: int) -> tuple[str, State | None]:
    """Decode LLM output 0-14 into (action, state).

    Encoding: 0=none, 1-7=add state, 8-14=remove state.
    State IDs match the State enum (on_fire=1 through molten=7).
    """
    if value == 0:
        return ("none", None)
    if 1 <= value <= 7:
        return ("add", State(value))
    if 8 <= value <= 14:
        return ("remove", State(value - 7))
    return ("none", None)
```

**`backend/app/models/blueprint.py`** — V3Blueprint (complete replacement).

```python
import uuid
from pydantic import BaseModel, Field


class VisualDescriptor(BaseModel):
    """Kept from V2 for image pipeline compatibility."""
    visual_description: str
    size_category: str


def height_to_size_category(height_cm: float) -> str:
    """Derive size category from height in cm."""
    if height_cm <= 5:
        return "tiny"
    if height_cm <= 50:
        return "small"
    if height_cm <= 200:
        return "medium"
    if height_cm <= 500:
        return "large"
    return "huge"


class V3Blueprint(BaseModel):
    """V3 object blueprint. All physics from LLM, no substances/tags."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str  # original player input

    # Physics (LLM-generated, stored in creation cache)
    mass: float = Field(ge=0.001, le=100000)   # kg, real-world
    height: float = Field(ge=1, le=5000)        # cm, integer from LLM
    friction: int = Field(ge=0, le=100)         # 0-100 scale
    bounce: int = Field(ge=0, le=100)           # 0-100 scale
    gravity: int = Field(ge=0, le=100)          # 0-100 scale

    # Destructibility
    armor: int = Field(ge=0, le=100)            # damage reduction %
    hp: int = Field(ge=0, le=100)               # total punishment pool
    indestructible: bool = False

    # Field
    has_field: bool = False
    field_range: int = Field(ge=0, le=5000, default=0)  # cm, 0 if no field

    # Classification
    autonomous: bool = False
    affordance: int = Field(ge=0, le=3, default=0)  # 0=carry, 1=mount, 2=climb, 3=nothing

    # Visual
    visual_description: str = ""
    size_category: str = "medium"

    # Derived (computed, not LLM-generated)
    damping: float = 0.0  # height_cm / (mass_kg * 100 + 10)

    @property
    def visual_descriptor(self) -> VisualDescriptor:
        """Compatibility shim for image pipeline (build_prompt, generate_sprite)."""
        return VisualDescriptor(
            visual_description=self.visual_description,
            size_category=self.size_category,
        )
```

**`backend/app/models/interactions.py`** — Pairwise interaction result.

```python
from pydantic import BaseModel, Field


class PairwiseResult(BaseModel):
    """Cached result of a pairwise interaction evaluation (9 LLM calls).

    A and B always refer to the first and second name in lexicographic sort order.
    The engine maps collision participants to cache A/B by sorting their names.

    State encoding 0-14:
        0=none
        1=add on_fire, 2=add frozen, 3=add wet, 4=add electrified,
        5=add poisoned, 6=add corroded, 7=add molten
        8=remove on_fire, 9=remove frozen, 10=remove wet, 11=remove electrified,
        12=remove poisoned, 13=remove corroded, 14=remove molten
    """
    damage_a: int = Field(ge=0, le=100, default=0)
    damage_b: int = Field(ge=0, le=100, default=0)
    state_change_a: int = Field(ge=0, le=14, default=0)
    state_change_b: int = Field(ge=0, le=14, default=0)
    force_b: int = Field(ge=0, le=100, default=0)
    direction_b: int = Field(ge=0, le=1, default=0)  # 0=push, 1=pull
    destroy_a: bool = False
    destroy_b: bool = False
    mode: int = Field(ge=0, le=1, default=0)  # 0=instant, 1=continuous
```

**`backend/app/models/behavior.py`** — Creature behavior result.

```python
from pydantic import BaseModel, Field


class CreatureBehavior(BaseModel):
    """Per creature×object pair behavior. Scene-local, not persistent.

    movement: 0=approach, 1=flee, 2=orbit, 3=ignore
    strength: 0-100 (used for utility scoring priority)
    action: 0=nothing, 1=damage, 2=heal, 3=add_state, 4=remove_state, 5=destroy, 6=take
    param: damage amount (0-100), state_id (1-7), or 0 for actions without params
    """
    movement: int = Field(ge=0, le=3, default=3)
    strength: int = Field(ge=0, le=100, default=0)
    action: int = Field(ge=0, le=6, default=0)
    param: int = Field(ge=0, le=100, default=0)
```

### Files to modify

**`backend/app/models/session.py`** — Update to reference V3Blueprint.

```python
from pydantic import BaseModel, Field

from app.models.blueprint import V3Blueprint


class WorldObject(BaseModel):
    object_id: str
    blueprint: V3Blueprint
    x: float = 0.0
    y: float = 0.0
    hp: float = 0.0
    states: list[int] = Field(default_factory=list)  # active State enum values


class Session(BaseModel):
    id: str
    created_at: str
    budget_used: float = 0.0
    budget_limit: float = 1.0
    objects: list[WorldObject] = Field(default_factory=list)

    @property
    def budget_remaining(self) -> float:
        return self.budget_limit - self.budget_used
```

### Validation

```bash
cd backend && uv run python -c "
from app.models.states import State, STATE_CONTRADICTIONS, decode_state_change
from app.models.blueprint import V3Blueprint, height_to_size_category
from app.models.interactions import PairwiseResult
from app.models.behavior import CreatureBehavior
from app.models.session import WorldObject, Session

# State decode round-trip
assert decode_state_change(0) == ('none', None)
assert decode_state_change(1) == ('add', State.ON_FIRE)
assert decode_state_change(8) == ('remove', State.ON_FIRE)
assert decode_state_change(7) == ('add', State.MOLTEN)
assert decode_state_change(14) == ('remove', State.MOLTEN)

# Blueprint construction
bp = V3Blueprint(name='fire sword', description='fire sword', mass=1.5, height=120,
    friction=30, bounce=10, gravity=50, armor=80, hp=90)
assert bp.visual_descriptor.size_category == 'medium'
assert height_to_size_category(3) == 'tiny'
assert height_to_size_category(800) == 'huge'

# Pairwise result
pr = PairwiseResult(damage_a=0, damage_b=40, state_change_b=1, force_b=20)
assert pr.mode == 0  # default instant

print('All Phase 2 checks passed')
"
```

---

## Phase 3 — Unified cache

**Why:** All LLM results flow through this. Creation cache is critical for correctness (same name → same physics). Pairwise cache is critical for performance (no LLM calls during gameplay).

### Files to create

**`backend/app/cache/__init__.py`** — Empty.

**`backend/app/cache/keys.py`** — Key normalization.

```python
def normalize_name(name: str) -> str:
    """Lowercase, strip, collapse internal whitespace to single space."""
    return " ".join(name.lower().strip().split())


def normalize_pair_key(name_a: str, name_b: str) -> str:
    """Normalized, lexicographically sorted pair key with :: separator."""
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    return f"{a}::{b}" if a <= b else f"{b}::{a}"


def pair_key_order(name_a: str, name_b: str) -> tuple[str, str, bool]:
    """Returns (first, second, swapped).

    first <= second lexicographically. swapped=True means name_a is second.
    Used to map collision participants to cache A/B positions.
    """
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if a <= b:
        return (a, b, False)
    return (b, a, True)
```

**`backend/app/cache/manager.py`** — Cache manager backed by `cache.db`.

```python
import json
import time

import aiosqlite


class CacheManager:
    """Unified LLM result cache backed by cache.db (separate from game.db).

    Cache types:
        "creation"   — key: "fire sword", value: all physics/affordance properties
        "pairwise"   — key: "fire sword::wooden shield", value: 9-field interaction outcome
    Creature behavior is scene-local (in-memory only, not here).
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    @classmethod
    async def create(cls, db_path: str) -> "CacheManager":
        """Create cache manager and ensure schema exists."""
        db = await aiosqlite.connect(db_path)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                cache_type TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                value_json TEXT NOT NULL,
                model_version TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (cache_type, cache_key)
            )
        """)
        await db.commit()
        return cls(db)

    async def get(self, cache_type: str, key: str) -> dict | None:
        """Return cached value or None."""
        async with self._db.execute(
            "SELECT value_json FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return json.loads(row[0])

    async def set(
        self, cache_type: str, key: str, value: dict, model_version: str
    ) -> None:
        """Write to cache (upsert)."""
        await self._db.execute(
            """INSERT OR REPLACE INTO cache (cache_type, cache_key, value_json,
               model_version, created_at) VALUES (?, ?, ?, ?, ?)""",
            (cache_type, key, json.dumps(value), model_version, time.time()),
        )
        await self._db.commit()

    async def exists(self, cache_type: str, key: str) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def delete(self, cache_type: str, key: str) -> None:
        await self._db.execute(
            "DELETE FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        await self._db.commit()

    async def get_all_pairs_for_object(self, name: str) -> list[tuple[str, dict]]:
        """Return all pairwise cache entries involving this object name."""
        normalized = name.lower().strip()
        async with self._db.execute(
            "SELECT cache_key, value_json FROM cache WHERE cache_type = 'pairwise' "
            "AND (cache_key LIKE ? OR cache_key LIKE ?)",
            (f"{normalized}::%", f"%::{normalized}"),
        ) as cursor:
            return [(row[0], json.loads(row[1])) async for row in cursor]

    async def close(self) -> None:
        await self._db.close()
```

**`backend/app/cache/scene_index.py`** — In-memory index for O(1) runtime lookups.

```python
from app.cache.keys import normalize_name, normalize_pair_key
from app.models.behavior import CreatureBehavior
from app.models.interactions import PairwiseResult


class SceneIndex:
    """In-memory index for a scene. Populated from cache.db at scene load,
    updated as new objects spawn. Keeps collision resolution at O(1) dict access.

    Pairwise results are persistent (backed by cache.db).
    Creature behaviors are scene-local (lost on scene change).
    """

    def __init__(self) -> None:
        self._pairs: dict[str, PairwiseResult] = {}
        self._behaviors: dict[str, CreatureBehavior] = {}

    def set_pair(self, key: str, result: PairwiseResult) -> None:
        self._pairs[key] = result

    def get_pair(self, name_a: str, name_b: str) -> PairwiseResult | None:
        key = normalize_pair_key(name_a, name_b)
        return self._pairs.get(key)

    def set_behavior(
        self, creature_name: str, object_name: str, behavior: CreatureBehavior
    ) -> None:
        key = normalize_pair_key(creature_name, object_name)
        self._behaviors[key] = behavior

    def get_behavior(
        self, creature_name: str, object_name: str
    ) -> CreatureBehavior | None:
        key = normalize_pair_key(creature_name, object_name)
        return self._behaviors.get(key)

    def invalidate_pairs_for(self, object_name: str) -> list[str]:
        """Mark all pairwise entries involving object_name as stale.
        Returns list of invalidated keys for lazy re-evaluation."""
        normalized = normalize_name(object_name)
        stale = [
            k for k in self._pairs
            if normalized in k.split("::")
        ]
        for k in stale:
            del self._pairs[k]
        return stale

    def clear_behaviors(self) -> None:
        """Clear all creature behaviors (scene-local, not persistent)."""
        self._behaviors.clear()
```

### Files to modify

**`backend/app/config.py`** — Add cache settings.

```python
# Add these fields to the Settings class:
cache_database_path: str = "data/cache.db"
cache_model_version: str = ""  # auto-derived from llm_model if empty
```

### Validation

```bash
cd backend && uv run python -c "
import asyncio
from app.cache.keys import normalize_name, normalize_pair_key, pair_key_order
from app.cache.manager import CacheManager

# Key normalization
assert normalize_name('  FIRE  SWORD ') == 'fire sword'
assert normalize_pair_key('wooden shield', 'fire sword') == 'fire sword::wooden shield'
assert normalize_pair_key('fire sword', 'wooden shield') == 'fire sword::wooden shield'

first, second, swapped = pair_key_order('wooden shield', 'fire sword')
assert first == 'fire sword'
assert second == 'wooden shield'
assert swapped is True

# Cache manager round-trip
async def test_cache():
    import tempfile, os
    path = os.path.join(tempfile.mkdtemp(), 'test_cache.db')
    cache = await CacheManager.create(path)

    # Write and read creation cache
    await cache.set('creation', 'fire sword', {'mass': 1.5, 'height': 120}, 'test-v1')
    result = await cache.get('creation', 'fire sword')
    assert result == {'mass': 1.5, 'height': 120}

    # Cache miss
    assert await cache.get('creation', 'ice wand') is None

    # Pairwise
    await cache.set('pairwise', 'fire sword::wooden shield', {'damage_b': 40}, 'test-v1')
    assert await cache.exists('pairwise', 'fire sword::wooden shield')

    await cache.close()
    print('All Phase 3 checks passed')

asyncio.run(test_cache())
"
```

---

## Phase 4 — LLM question runner

**Why:** Generic infrastructure for all V3 LLM calls. Used by creation (Phase 5), pairwise (Phase 6), and creature behavior (Phase 7).

### Files to create

**`backend/app/llm/__init__.py`** — Empty.

**`backend/app/llm/model.py`** — Shared model builder (extracted from V2's `creator/agent.py`).

```python
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIModel

from app.config import settings


_model: Model | str | None = None


def build_model() -> Model | str:
    """Route to local SGLang (OpenAI-compatible) or cloud model based on config.

    Reuse the same logic from V2's _build_model() in creator/agent.py:
    - If LOCAL_LLM_URL is set: OpenAIModel pointing at SGLang endpoint
    - Otherwise: settings.llm_model string (PydanticAI resolves provider from prefix)
    """
    global _model
    if _model is not None:
        return _model

    if settings.local_llm_url:
        from httpx import AsyncClient
        _model = OpenAIModel(
            model_name=settings.llm_model,
            base_url=settings.local_llm_url + "/v1",
            http_client=AsyncClient(timeout=settings.llm_timeout),
        )
    else:
        _model = settings.llm_model

    return _model
```

**`backend/app/llm/questions.py`** — Question data class and question lists.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    """A single LLM question. Prompt may contain {name}, {name_a}, {name_b}, etc."""
    key: str
    prompt: str
    max_tokens: int = 1
    output_type: type = int  # int for 1-token, str for visual description, float for mass


# === Object creation questions (13 + 1 visual) ===

CREATION_QUESTIONS: list[Question] = [
    Question(
        key="mass",
        prompt="How heavy is {name} in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500, house=50000)",
        max_tokens=4,
        output_type=float,
    ),
    Question(
        key="height",
        prompt="How tall is {name} in cm? (ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800)",
        max_tokens=2,
    ),
    Question(
        key="friction",
        prompt="How grippy is {name} 0-100? (ice=0, metal=30, wood=50, rubber=90)",
        max_tokens=1,
    ),
    Question(
        key="bounce",
        prompt="How bouncy is {name} 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)",
        max_tokens=1,
    ),
    Question(
        key="gravity",
        prompt="Gravity pull on {name} 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75)",
        max_tokens=1,
    ),
    Question(
        key="armor",
        prompt="How resistant to damage is {name} 0-100? (paper=5, wood=30, steel=80, diamond=99)",
        max_tokens=1,
    ),
    Question(
        key="hp",
        prompt="How much punishment before {name} is destroyed 0-100? (balloon=5, wood=40, steel=80)",
        max_tokens=1,
    ),
    Question(
        key="indestructible",
        prompt="Can {name} be destroyed? 0=no 1=yes",
        max_tokens=1,
    ),
    Question(
        key="has_field",
        prompt="Does {name} affect nearby things without touching? 0=no 1=yes (campfire=1, magnet=1, sword=0, rock=0)",
        max_tokens=1,
    ),
    Question(
        key="field_range",
        prompt="How far does {name} affect nearby things, in cm? (candle=50, campfire=250, bonfire=500, volcano=1000, none=0)",
        max_tokens=2,
    ),
    Question(
        key="autonomous",
        prompt="Is {name} a creature that moves on its own? 0=no 1=yes (zombie=1, dog=1, sword=0, tree=0)",
        max_tokens=1,
    ),
    Question(
        key="affordance",
        prompt="When a player interacts with {name}: 0=carry it 1=ride it 2=climb it 3=nothing (sword=0, horse=1, ladder=2, mountain=3)",
        max_tokens=1,
    ),
]

VISUAL_QUESTION = Question(
    key="visual",
    prompt=(
        "Describe {name} for a sprite artist in 1-2 sentences. "
        "Focus on shape, material, and color. No background."
    ),
    max_tokens=30,
    output_type=str,
)


# === Pairwise interaction questions (9 per pair) ===

PAIRWISE_QUESTIONS: list[Question] = [
    Question(key="damage_a", prompt="{context} Damage to {name_a}? 0-100"),
    Question(key="damage_b", prompt="{context} Damage to {name_b}? 0-100"),
    Question(
        key="state_change_a",
        prompt="{context} State change on {name_a}? 0=none, 1=catch fire, 2=freeze, 3=get wet, 4=electrify, 5=poison, 6=corrode, 7=melt, 8=extinguish, 9=thaw, 10=dry, 11=de-electrify, 12=cure poison, 13=de-corrode, 14=cool from molten",
    ),
    Question(
        key="state_change_b",
        prompt="{context} State change on {name_b}? 0=none, 1=catch fire, 2=freeze, 3=get wet, 4=electrify, 5=poison, 6=corrode, 7=melt, 8=extinguish, 9=thaw, 10=dry, 11=de-electrify, 12=cure poison, 13=de-corrode, 14=cool from molten",
    ),
    Question(key="force_b", prompt="{context} Force applied to {name_b}? 0-100 (0=none, 50=moderate shove, 100=explosive launch)"),
    Question(key="direction_b", prompt="{context} Push or pull {name_b}? 0=push 1=pull"),
    Question(key="destroy_a", prompt="{context} Is {name_a} destroyed? 0=no 1=yes"),
    Question(key="destroy_b", prompt="{context} Is {name_b} destroyed? 0=no 1=yes"),
    Question(key="mode", prompt="{context} Is the effect instant or continuous? 0=instant 1=continuous (fire burning wood=1, rock hitting glass=0)"),
]


# === Creature behavior questions (staged) ===

CREATURE_MOVEMENT_QUESTION = Question(
    key="movement",
    prompt="Scene: [{scene}]. {creature} sees {target}. 0=approach 1=flee 2=orbit 3=ignore",
)

CREATURE_STRENGTH_QUESTION = Question(
    key="strength",
    prompt="Scene: [{scene}]. How strongly does {creature} react to {target}? 0=ignores 25=mild 50=moderate 75=strong 100=absolute priority",
)

CREATURE_ACTION_QUESTION = Question(
    key="action",
    prompt="{creature} is {movement_desc} {target} and {motivation}. On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take",
)

CREATURE_PARAM_QUESTION = Question(
    key="param",
    prompt="{creature} will {action_desc} {target}. {param_prompt}",
)
```

**`backend/app/llm/runner.py`** — Parallel question executor.

```python
import asyncio
import logging
from typing import Any

from pydantic_ai import Agent

from app.llm.model import build_model
from app.llm.questions import Question

logger = logging.getLogger(__name__)


async def ask_one(
    question: Question,
    format_kwargs: dict[str, str],
    *,
    system_prompt: str = "",
) -> tuple[str, Any]:
    """Ask a single question using a PydanticAI Agent.

    Returns (question.key, parsed_answer).
    On failure, returns (question.key, None).
    """
    prompt = question.prompt.format(**format_kwargs)
    model = build_model()

    agent: Agent[None, Any] = Agent(
        model,
        output_type=question.output_type,
        system_prompt=system_prompt if system_prompt else None,
        retries=2,
    )

    try:
        result = await agent.run(prompt)
        return (question.key, result.output)
    except Exception:
        logger.exception("LLM call failed for question %s", question.key)
        return (question.key, None)


async def ask_questions(
    questions: list[Question],
    format_kwargs: dict[str, str],
    *,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Fire all questions in parallel via asyncio.gather().

    Returns {key: answer}. Failed questions have value None.
    """
    tasks = [
        ask_one(q, format_kwargs, system_prompt=system_prompt)
        for q in questions
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output: dict[str, Any] = {}
    for r in results:
        if isinstance(r, Exception):
            logger.error("Question task exception: %s", r)
            continue
        key, value = r
        output[key] = value

    return output
```

### Validation

```bash
cd backend && uv run python -c "
from app.llm.questions import CREATION_QUESTIONS, VISUAL_QUESTION, PAIRWISE_QUESTIONS

# All creation questions have unique keys
keys = [q.key for q in CREATION_QUESTIONS]
assert len(keys) == len(set(keys)), f'Duplicate keys: {keys}'
assert len(CREATION_QUESTIONS) == 12  # 12 property questions

# All use {name} placeholder
for q in CREATION_QUESTIONS:
    assert '{name}' in q.prompt, f'{q.key} missing {{name}}'

# Pairwise questions
assert len(PAIRWISE_QUESTIONS) == 9
for q in PAIRWISE_QUESTIONS:
    assert '{context}' in q.prompt, f'{q.key} missing {{context}}'

# Visual question
assert VISUAL_QUESTION.output_type is str
assert VISUAL_QUESTION.max_tokens == 30

print('All Phase 4 checks passed')
"
```

---

## Phase 5 — Creation pipeline

**Why:** Player types a description → backend returns a V3Blueprint with LLM-generated physics. This is the core gameplay loop.

### Files to create

**`backend/app/creator/create.py`** — Replaces `creator/agent.py`.

```python
import logging
import uuid

from app.cache.keys import normalize_name
from app.cache.manager import CacheManager
from app.config import settings
from app.llm.questions import CREATION_QUESTIONS, VISUAL_QUESTION
from app.llm.runner import ask_questions
from app.models.blueprint import V3Blueprint, height_to_size_category

logger = logging.getLogger(__name__)


def _clamp(value: int | float | None, min_val: float, max_val: float, default: float) -> float:
    """Clamp a value to range, using default if None."""
    if value is None:
        return default
    return max(min_val, min(max_val, float(value)))


def _clamp_int(value: int | None, min_val: int, max_val: int, default: int) -> int:
    if value is None:
        return default
    return max(min_val, min(max_val, int(value)))


async def create_object(name: str, cache: CacheManager) -> V3Blueprint:
    """Create a V3Blueprint from a player description.

    1. Check creation cache (exact name match after normalization)
    2. If miss: fire all LLM questions in parallel (~200ms)
    3. Clamp/validate results
    4. Compute derived fields (damping, size_category)
    5. Write to creation cache
    6. Return blueprint with fresh UUID
    """
    normalized = normalize_name(name)
    model_version = settings.cache_model_version or settings.llm_model

    # 1. Cache check
    cached = await cache.get("creation", normalized)
    if cached is not None:
        return V3Blueprint(id=str(uuid.uuid4()), **cached)

    # 2. Fire all questions in parallel
    results = await ask_questions(
        CREATION_QUESTIONS + [VISUAL_QUESTION],
        {"name": name},
    )

    # 3. Clamp and validate
    mass = _clamp(results.get("mass"), 0.001, 100000, 1.0)
    height = _clamp(results.get("height"), 1, 5000, 100)
    friction = _clamp_int(results.get("friction"), 0, 100, 30)
    bounce = _clamp_int(results.get("bounce"), 0, 100, 10)
    gravity = _clamp_int(results.get("gravity"), 0, 100, 50)
    armor = _clamp_int(results.get("armor"), 0, 100, 20)
    hp = _clamp_int(results.get("hp"), 0, 100, 50)
    indestructible = bool(results.get("indestructible", 0) == 0)  # 0=no(indestructible), 1=yes(destructible)
    has_field = bool(results.get("has_field", 0) == 1)
    field_range = _clamp_int(results.get("field_range"), 0, 5000, 0) if has_field else 0
    autonomous = bool(results.get("autonomous", 0) == 1)
    affordance = _clamp_int(results.get("affordance"), 0, 3, 0)
    visual_desc = str(results.get("visual", f"a {name}"))

    # 4. Derived fields
    damping = height / (mass * 100 + 10)
    size_cat = height_to_size_category(height)

    # 5. Build cache data (excludes id — each instance gets a fresh UUID)
    blueprint_data = {
        "name": name,
        "description": name,
        "mass": mass,
        "height": height,
        "friction": friction,
        "bounce": bounce,
        "gravity": gravity,
        "armor": armor,
        "hp": hp,
        "indestructible": indestructible,
        "has_field": has_field,
        "field_range": field_range,
        "autonomous": autonomous,
        "affordance": affordance,
        "visual_description": visual_desc,
        "size_category": size_cat,
        "damping": damping,
    }
    await cache.set("creation", normalized, blueprint_data, model_version)

    # 6. Return with fresh ID
    return V3Blueprint(id=str(uuid.uuid4()), **blueprint_data)
```

### Files to modify

**`backend/app/routers/objects.py`** — Replace V2 creation call with V3.

Key changes:
- Import `from app.creator.create import create_object`
- `CreateObjectResponse` returns V3Blueprint dict (not GameObjectBlueprint)
- Endpoint body: `blueprint = await create_object(body.description, cache=request.app.state.cache)`
- Sprite generation still works via `blueprint.name` and `blueprint.visual_descriptor`
- Background task for spawn integration (Phase 6) will be added later

**`backend/app/main.py`** — Wire up cache.db.

Key changes in `lifespan()`:
- `from app.cache.manager import CacheManager`
- After game.db init: `app.state.cache = await CacheManager.create(settings.cache_database_path)`
- Remove rules router include: delete `app.include_router(rules.router)`
- Remove V2 agent warmup
- In shutdown: `await app.state.cache.close()`

**`backend/app/sessions/manager.py`** — Update to V3Blueprint.

- `from app.models.blueprint import V3Blueprint`
- `save_object`: serializes `blueprint.model_dump_json()`
- `get_session` / `get_object_blueprint`: deserializes with `V3Blueprint.model_validate_json()`

**`backend/app/images/pipeline.py`** — Update import.

- `from app.models.blueprint import V3Blueprint, VisualDescriptor`
- `generate_sprite(blueprint: V3Blueprint)` — same interface, just type annotation change
- `build_prompt(name, visual_descriptor)` — unchanged, VisualDescriptor interface preserved

**`backend/app/cli.py`** — Wire up V3 creation CLI.

```python
# cmd_create changes:
async def cmd_create(description: str):
    from app.cache.manager import CacheManager
    from app.creator.create import create_object
    cache = await CacheManager.create("data/cache.db")
    try:
        blueprint = await create_object(description, cache)
        print(blueprint.model_dump_json(indent=2))
    finally:
        await cache.close()
```

### Validation

```bash
make cli-create PROMPT="fire sword"  # V3Blueprint JSON with all expected fields
make cli-create PROMPT="fire sword"  # Second call: identical values (cache hit)
make cli-create PROMPT="FIRE SWORD"  # Same cache entry (key normalization)
make cli-sprite PROMPT="fire sword"  # Sprite generated (image pipeline works)
```

---

## Phase 6 — Pairwise interaction system

**Why:** When a new object enters a scene, screen it against existing objects, fully evaluate interesting pairs, cache results. Runtime collision resolution is a dict lookup.

### Files to create

**`backend/app/engine/__init__.py`** — Empty (may already exist).

**`backend/app/engine/screening.py`** — Pairwise screening (1 LLM call per new object).

```python
import logging
import re

from pydantic_ai import Agent

from app.llm.model import build_model
from app.models.blueprint import V3Blueprint

logger = logging.getLogger(__name__)


def _describe_for_screening(bp: V3Blueprint) -> str:
    """Build a short description for screening prompts."""
    parts = [f"{bp.name}: {bp.mass}kg, armor {bp.armor}, hp {bp.hp}"]
    if bp.has_field:
        parts.append(f"field {bp.field_range}cm")
    if bp.autonomous:
        parts.append("creature")
    return ", ".join(parts)


async def screen_pairs(
    new_object: V3Blueprint,
    scene_objects: list[V3Blueprint],
) -> list[int]:
    """Single LLM call: which scene objects would interact interestingly?

    Returns indices into scene_objects (0-based).
    Output is a comma-separated list of 1-based numbers, parsed to 0-based indices.
    On failure, returns all indices (safe fallback: evaluate everything).
    """
    if not scene_objects:
        return []

    new_desc = _describe_for_screening(new_object)
    lines = []
    for i, obj in enumerate(scene_objects):
        lines.append(f"  {i + 1}. {_describe_for_screening(obj)}")
    object_list = "\n".join(lines)

    prompt = (
        f"New object: {new_desc}.\n"
        f"Scene objects:\n{object_list}\n"
        f"Which would interact interestingly with {new_object.name}? "
        f"List numbers, comma-separated. If none, say 'none'."
    )

    model = build_model()
    agent: Agent[None, str] = Agent(model, output_type=str, retries=2)

    try:
        result = await agent.run(prompt)
        text = result.output.strip().lower()
        if text == "none" or not text:
            return []
        numbers = re.findall(r"\d+", text)
        indices = [int(n) - 1 for n in numbers if 0 < int(n) <= len(scene_objects)]
        return sorted(set(indices))
    except Exception:
        logger.exception("Screening call failed, falling back to all pairs")
        return list(range(len(scene_objects)))
```

**`backend/app/engine/pairwise.py`** — Full pairwise evaluation (9 parallel calls per pair).

```python
import logging

from app.cache.keys import normalize_pair_key, pair_key_order
from app.cache.manager import CacheManager
from app.config import settings
from app.llm.questions import PAIRWISE_QUESTIONS
from app.llm.runner import ask_questions
from app.models.blueprint import V3Blueprint
from app.models.interactions import PairwiseResult

logger = logging.getLogger(__name__)


def describe_object(bp: V3Blueprint, states: list[int] | None = None) -> str:
    """Build description string for pairwise prompts.

    Includes physics properties as calibration anchors.
    Includes active states if provided (for re-evaluation after state change).
    """
    parts = [f"{bp.name}: {bp.mass}kg, armor {bp.armor}, hp {bp.hp}"]
    if bp.has_field:
        parts.append(f"field {bp.field_range}cm")
    if states:
        from app.models.states import STATE_NAMES
        state_names = [STATE_NAMES.get(s, str(s)) for s in states]
        parts.append(f"[{', '.join(state_names)}]")
    return ", ".join(parts)


async def evaluate_pair(
    blueprint_a: V3Blueprint,
    blueprint_b: V3Blueprint,
    cache: CacheManager,
    *,
    states_a: list[int] | None = None,
    states_b: list[int] | None = None,
) -> PairwiseResult:
    """Evaluate one pair: 9 parallel 1-token LLM calls. Cache result.

    A and B are the first and second name in lexicographic sort order.
    If the caller's objects are in different order, the results are mapped accordingly.
    """
    first, second, swapped = pair_key_order(blueprint_a.name, blueprint_b.name)
    bp_first = blueprint_b if swapped else blueprint_a
    bp_second = blueprint_a if swapped else blueprint_b
    states_first = states_b if swapped else states_a
    states_second = states_a if swapped else states_b

    pair_key = f"{first}::{second}"
    model_version = settings.cache_model_version or settings.llm_model

    # Check cache (skip if states provided — re-evaluation)
    if states_a is None and states_b is None:
        cached = await cache.get("pairwise", pair_key)
        if cached is not None:
            return PairwiseResult(**cached)

    # Build context string (input is free — include everything)
    desc_a = describe_object(bp_first, states_first)
    desc_b = describe_object(bp_second, states_second)
    context = f"[{desc_a}] collides with [{desc_b}]."

    results = await ask_questions(
        PAIRWISE_QUESTIONS,
        {
            "context": context,
            "name_a": bp_first.name,
            "name_b": bp_second.name,
        },
    )

    # Clamp and assemble
    pr = PairwiseResult(
        damage_a=max(0, min(100, int(results.get("damage_a") or 0))),
        damage_b=max(0, min(100, int(results.get("damage_b") or 0))),
        state_change_a=max(0, min(14, int(results.get("state_change_a") or 0))),
        state_change_b=max(0, min(14, int(results.get("state_change_b") or 0))),
        force_b=max(0, min(100, int(results.get("force_b") or 0))),
        direction_b=max(0, min(1, int(results.get("direction_b") or 0))),
        destroy_a=bool(results.get("destroy_a", 0)),
        destroy_b=bool(results.get("destroy_b", 0)),
        mode=max(0, min(1, int(results.get("mode") or 0))),
    )

    # Cache
    await cache.set("pairwise", pair_key, pr.model_dump(), model_version)

    return pr
```

**`backend/app/engine/resolver.py`** — V3 interaction resolver (cache-backed).

```python
from app.cache.keys import pair_key_order
from app.cache.scene_index import SceneIndex
from app.models.interactions import PairwiseResult


class InteractionResolver:
    """Resolves pairwise interactions from the scene index (cache-backed).

    Returns None for uncached pairs (safe default: nothing happens).
    """

    def __init__(self, scene_index: SceneIndex) -> None:
        self._index = scene_index

    def resolve(
        self, name_a: str, name_b: str
    ) -> tuple[PairwiseResult | None, bool]:
        """Look up cached interaction.

        Returns (result, swapped) where swapped=True means name_a maps to cache B.
        Returns (None, False) if pair not cached.
        """
        result = self._index.get_pair(name_a, name_b)
        if result is None:
            return (None, False)
        _, _, swapped = pair_key_order(name_a, name_b)
        return (result, swapped)
```

**`backend/app/engine/spawn.py`** — Spawn integration orchestrator.

```python
import asyncio
import logging

from app.cache.manager import CacheManager
from app.cache.scene_index import SceneIndex
from app.engine.pairwise import evaluate_pair
from app.engine.screening import screen_pairs
from app.models.blueprint import V3Blueprint

logger = logging.getLogger(__name__)


async def integrate_new_object(
    new_object: V3Blueprint,
    scene_objects: list[V3Blueprint],
    cache: CacheManager,
    scene_index: SceneIndex,
) -> None:
    """Background task: screen + evaluate pairwise interactions for a new object.

    Runs during sprite generation window (2-5s). Player doesn't wait for this.

    1. Screen: which existing objects interact interestingly? (1 call, ~100-160ms)
    2. For each interesting pair, check pairwise cache
    3. Evaluate uncached pairs (9 parallel calls each, ~145ms per batch)
    4. Store results in cache + scene index
    """
    if not scene_objects:
        return

    # 1. Screen
    interesting_indices = await screen_pairs(new_object, scene_objects)
    logger.info(
        "Screening %s against %d objects: %d interesting pairs",
        new_object.name,
        len(scene_objects),
        len(interesting_indices),
    )

    if not interesting_indices:
        return

    # 2-3. Evaluate interesting pairs
    async def eval_one(scene_obj: V3Blueprint) -> None:
        result = await evaluate_pair(new_object, scene_obj, cache)
        from app.cache.keys import normalize_pair_key
        key = normalize_pair_key(new_object.name, scene_obj.name)
        scene_index.set_pair(key, result)

    tasks = [eval_one(scene_objects[i]) for i in interesting_indices]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info("Spawn integration complete for %s", new_object.name)
```

### Files to modify

**`backend/app/routers/objects.py`** — Schedule spawn integration as background task.

After blueprint creation and sprite generation scheduling, add:

```python
# Schedule pairwise evaluation in background
session = await session_mgr.get_session(session_id)
scene_blueprints = [obj.blueprint for obj in session.objects if obj.object_id != blueprint.id]
background_tasks.add(
    asyncio.create_task(
        integrate_new_object(blueprint, scene_blueprints, cache, scene_index)
    )
)
```

### Validation

```bash
cd backend && uv run python -c "
from app.cache.keys import pair_key_order

# Verify key ordering
first, second, swapped = pair_key_order('wooden shield', 'fire sword')
assert first == 'fire sword'
assert second == 'wooden shield'
assert swapped is True

# Verify resolver returns None for uncached
from app.cache.scene_index import SceneIndex
from app.engine.resolver import InteractionResolver
idx = SceneIndex()
resolver = InteractionResolver(idx)
result, swapped = resolver.resolve('fire sword', 'wooden shield')
assert result is None

# Verify resolver finds cached entries
from app.models.interactions import PairwiseResult
pr = PairwiseResult(damage_b=40, state_change_b=1)
idx.set_pair('fire sword::wooden shield', pr)
result, swapped = resolver.resolve('fire sword', 'wooden shield')
assert result is not None
assert result.damage_b == 40
result2, swapped2 = resolver.resolve('wooden shield', 'fire sword')
assert result2.damage_b == 40  # same entry
assert swapped2 is True  # wooden shield is B

print('All Phase 6 checks passed')
"
```

---

## Phase 7 — Creature behavior

**Why:** Autonomous creatures need per-pair behavior: movement pattern + on-arrival action. Evaluated in 3 sequential stages, each internally parallel.

### Files to create

**`backend/app/engine/behavior.py`** — Staged creature behavior evaluation.

```python
import asyncio
import logging

from app.cache.scene_index import SceneIndex
from app.llm.questions import (
    CREATURE_ACTION_QUESTION,
    CREATURE_MOVEMENT_QUESTION,
    CREATURE_PARAM_QUESTION,
    CREATURE_STRENGTH_QUESTION,
)
from app.llm.runner import ask_one
from app.models.behavior import CreatureBehavior
from app.models.blueprint import V3Blueprint

logger = logging.getLogger(__name__)

# Movement type → motivation text for seeding stage 2 prompts
_MOVEMENT_MOTIVATION = {
    0: ("APPROACHING", "wants to interact with"),
    2: ("ORBITING", "is cautious about"),
}

# Action type → parameter prompt
_ACTION_PARAM_PROMPTS = {
    1: "How much damage? 0-100",          # damage
    2: "How much healing? 0-100",          # heal
    3: "Which state to add? 1=on_fire 2=frozen 3=wet 4=electrified 5=poisoned 6=corroded 7=molten",
    4: "Which state to remove? 1=on_fire 2=frozen 3=wet 4=electrified 5=poisoned 6=corroded 7=molten",
}

# Action type → description text for seeding stage 3 prompts
_ACTION_DESCRIPTIONS = {
    0: "do nothing to",
    1: "damage",
    2: "heal",
    3: "add a state to",
    4: "remove a state from",
    5: "destroy",
    6: "take",
}


async def evaluate_creature_behaviors(
    creature: V3Blueprint,
    scene_objects: list[V3Blueprint],
    scene_index: SceneIndex,
) -> dict[str, CreatureBehavior]:
    """3-stage evaluation for one creature against all scene objects.

    Stage 1+1b (parallel): movement (0-3) + strength (0-100) for all pairs
    Stage 2 (parallel, filtered): action (0-6) for approach/orbit pairs only
    Stage 3 (parallel, filtered): parameters for actions that need them

    Returns {normalized_object_name: CreatureBehavior}.
    Stores results in scene_index (scene-local, not persistent cache).
    """
    if not scene_objects:
        return {}

    scene_desc = ", ".join(obj.name for obj in scene_objects)
    results: dict[str, CreatureBehavior] = {}

    # === Stage 1+1b: Movement + Strength (all pairs, parallel) ===
    stage1_tasks = []
    for obj in scene_objects:
        kwargs = {"scene": scene_desc, "creature": creature.name, "target": obj.name}
        stage1_tasks.append(ask_one(CREATURE_MOVEMENT_QUESTION, kwargs))
        stage1_tasks.append(ask_one(CREATURE_STRENGTH_QUESTION, kwargs))

    stage1_results = await asyncio.gather(*stage1_tasks, return_exceptions=True)

    # Parse stage 1 results
    stage1_data: dict[str, dict] = {}
    for i, obj in enumerate(scene_objects):
        mv_result = stage1_results[i * 2]
        st_result = stage1_results[i * 2 + 1]

        movement = 3  # default: ignore
        strength = 0
        if not isinstance(mv_result, Exception):
            movement = max(0, min(3, int(mv_result[1] or 3)))
        if not isinstance(st_result, Exception):
            strength = max(0, min(100, int(st_result[1] or 0)))

        stage1_data[obj.name] = {"movement": movement, "strength": strength}

        # Flee and ignore pairs are complete
        if movement in (1, 3):
            results[obj.name] = CreatureBehavior(movement=movement, strength=strength)

    # === Stage 2: Action (approach/orbit pairs only, parallel) ===
    approach_orbit = {
        name: data for name, data in stage1_data.items()
        if data["movement"] in (0, 2)
    }

    if approach_orbit:
        stage2_tasks = []
        stage2_names = []
        for name, data in approach_orbit.items():
            mv = data["movement"]
            mv_desc, motivation = _MOVEMENT_MOTIVATION[mv]
            kwargs = {
                "creature": creature.name,
                "target": name,
                "movement_desc": mv_desc,
                "motivation": motivation,
            }
            stage2_tasks.append(ask_one(CREATURE_ACTION_QUESTION, kwargs))
            stage2_names.append(name)

        stage2_results = await asyncio.gather(*stage2_tasks, return_exceptions=True)

        for name, result in zip(stage2_names, stage2_results):
            action = 0
            if not isinstance(result, Exception):
                action = max(0, min(6, int(result[1] or 0)))
            stage1_data[name]["action"] = action

    # === Stage 3: Parameters (actions that need them, parallel) ===
    needs_params = {
        name: data for name, data in stage1_data.items()
        if data.get("action", 0) in _ACTION_PARAM_PROMPTS
    }

    if needs_params:
        stage3_tasks = []
        stage3_names = []
        for name, data in needs_params.items():
            action = data["action"]
            kwargs = {
                "creature": creature.name,
                "target": name,
                "action_desc": _ACTION_DESCRIPTIONS[action],
                "param_prompt": _ACTION_PARAM_PROMPTS[action],
            }
            stage3_tasks.append(ask_one(CREATURE_PARAM_QUESTION, kwargs))
            stage3_names.append(name)

        stage3_results = await asyncio.gather(*stage3_tasks, return_exceptions=True)

        for name, result in zip(stage3_names, stage3_results):
            param = 0
            if not isinstance(result, Exception):
                param = max(0, min(100, int(result[1] or 0)))
            stage1_data[name]["param"] = param

    # === Assemble final results ===
    for name, data in stage1_data.items():
        if name not in results:  # skip flee/ignore (already added)
            behavior = CreatureBehavior(
                movement=data["movement"],
                strength=data["strength"],
                action=data.get("action", 0),
                param=data.get("param", 0),
            )
            results[name] = behavior

    # Store in scene index
    for name, behavior in results.items():
        scene_index.set_behavior(creature.name, name, behavior)

    return results
```

### Files to modify

**`backend/app/engine/spawn.py`** — Extend to include creature behavior evaluation.

After pairwise evaluation, add:

```python
# Creature behavior: if new object is autonomous, evaluate against all scene objects
if new_object.autonomous:
    from app.engine.behavior import evaluate_creature_behaviors
    await evaluate_creature_behaviors(new_object, scene_objects, scene_index)

# Also: for all existing autonomous creatures, evaluate them against the new object
for obj in scene_objects:
    if obj.autonomous:
        from app.engine.behavior import evaluate_creature_behaviors
        await evaluate_creature_behaviors(obj, [new_object], scene_index)
```

### Validation

```bash
# Unit test with mocked LLM:
# 1. Create "zombie cop" (autonomous) + "donut" + "fire" + "citizen"
# 2. Verify stage 1 produces movement+strength for all 3 pairs
# 3. Verify stage 2 only runs for approach/orbit pairs (filter works)
# 4. Verify results stored in scene_index
# 5. Verify scene context included in all prompts
```

At this point, `make check` should pass on the backend (lint + typecheck on the new code). Tests require mocking the LLM — write those in Phase 9.

---

## Phase 8 — Godot client rewrite

**Why:** The client currently uses tags, substances, and static rules. All of that is replaced by the pairwise cache and states.

This phase has internal parallelism: steps 8.1-8.2 (data layer) must be first, but 8.3-8.7 can be worked in any order after that.

### Step 8.1 — New data layer (create first, no behavior changes)

**Create `godot/scripts/data/state_config.gd`** — Replaces tag_contradictions.gd, tag_colors.gd, tag_descriptions.gd, tag_animations.gd, field_config.gd (5 files → 1).

```gdscript
class_name StateConfig

enum State { NONE = 0, ON_FIRE = 1, FROZEN = 2, WET = 3, ELECTRIFIED = 4, POISONED = 5, CORRODED = 6, MOLTEN = 7 }

const CONTRADICTIONS: Dictionary = {
    State.ON_FIRE: [State.FROZEN, State.WET],
    State.FROZEN: [State.ON_FIRE, State.MOLTEN],
    State.WET: [State.ON_FIRE],
    State.MOLTEN: [State.FROZEN],
}

const NAMES: Dictionary = {
    State.ON_FIRE: "on_fire", State.FROZEN: "frozen", State.WET: "wet",
    State.ELECTRIFIED: "electrified", State.POISONED: "poisoned",
    State.CORRODED: "corroded", State.MOLTEN: "molten",
}

const COLORS: Dictionary = {
    State.ON_FIRE: Color("#FF4444"), State.FROZEN: Color("#4488FF"),
    State.WET: Color("#4499DD"), State.ELECTRIFIED: Color("#FFDD44"),
    State.POISONED: Color("#44AA22"), State.CORRODED: Color("#887744"),
    State.MOLTEN: Color("#FF6600"),
}

const DESCRIPTIONS: Dictionary = {
    State.ON_FIRE: "Burning. DOT. Spreads to nearby objects.",
    State.FROZEN: "Immobilized. Extra impact damage.",
    State.WET: "Amplifies electrified damage. Resists on_fire.",
    State.ELECTRIFIED: "DOT. Chains to nearby wet objects.",
    State.POISONED: "DOT. Doesn't spread.",
    State.CORRODED: "Armor reduced. Incoming damage increased.",
    State.MOLTEN: "Contact damage. Eventually destroys self.",
}

const HEAL_COLOR: Color = Color("#44FF88")
const DEFAULT_COLOR: Color = Color("#AAAAAA")
const STATE_DECAY_DURATION: float = 10.0

# Particle configs per state (adapted from V2 TagAnimations)
# Each: {direction, color, amount, speed, lifetime, spread}
const PARTICLES: Dictionary = {
    State.ON_FIRE: {direction=Vector2(0, -1), color=Color("#FF6600"), amount=8, speed=40.0, lifetime=0.8, spread=30.0},
    State.WET: {direction=Vector2(0, 1), color=Color("#4499DD"), amount=4, speed=20.0, lifetime=0.6, spread=15.0},
    State.ELECTRIFIED: {direction=Vector2.ZERO, color=Color("#FFDD44"), amount=6, speed=60.0, lifetime=0.3, spread=180.0},
    State.POISONED: {direction=Vector2(0, -1), color=Color("#44AA22"), amount=4, speed=25.0, lifetime=0.7, spread=20.0},
    State.CORRODED: {direction=Vector2(0, 1), color=Color("#887744"), amount=3, speed=15.0, lifetime=0.5, spread=10.0},
    State.MOLTEN: {direction=Vector2(0, -1), color=Color("#FF6600"), amount=6, speed=30.0, lifetime=0.9, spread=25.0},
}

# Color shift per state (applied to sprite modulate)
const COLOR_SHIFT: Dictionary = {
    State.FROZEN: {target_color=Color(0.6, 0.8, 1.0), blend=0.4},
    State.POISONED: {target_color=Color(0.6, 1.0, 0.6), blend=0.3},
    State.CORRODED: {target_color=Color(0.8, 0.7, 0.5), blend=0.3},
}

# Flash configs per state (periodic brightness pulse)
const FLASH: Dictionary = {
    State.ON_FIRE: {interval=0.15, intensity=1.3},
    State.ELECTRIFIED: {interval=0.4, intensity=1.5},  # random interval in practice
}

# Shader per state
const SHADERS: Dictionary = {
    State.MOLTEN: "res://shaders/ripple.gdshader",
    # State.FROZEN: "res://shaders/ice.gdshader",  # NEW shader needed
}
```

**Create `godot/scripts/data/interaction_cache.gd`** — New autoload replacing RuleEngine.

```gdscript
class_name InteractionCache
extends Node

## Pairwise interaction outcomes: "name_a::name_b" -> Dictionary
var _pairwise: Dictionary = {}

## Creature behavior data: "creature_name::target_name" -> Dictionary
var _creature_behaviors: Dictionary = {}


static func make_pair_key(name_a: String, name_b: String) -> String:
    var a := name_a.strip_edges().to_lower()
    var b := name_b.strip_edges().to_lower()
    if a <= b:
        return "%s::%s" % [a, b]
    return "%s::%s" % [b, a]


func store_pairwise(pair_key: String, data: Dictionary) -> void:
    _pairwise[pair_key] = data


func lookup_pairwise(name_a: String, name_b: String) -> Dictionary:
    ## Returns {} if uncached (safe default: nothing happens).
    var key := make_pair_key(name_a, name_b)
    return _pairwise.get(key, {})


func resolve_ab(name_a: String, name_b: String) -> Dictionary:
    ## Returns {pair: Dictionary, a_is_first: bool}.
    ## a_is_first=true means name_a maps to cache's A fields (damage_a, etc).
    var a := name_a.strip_edges().to_lower()
    var b := name_b.strip_edges().to_lower()
    var key := make_pair_key(name_a, name_b)
    var pair: Dictionary = _pairwise.get(key, {})
    return {"pair": pair, "a_is_first": a <= b}


func store_creature_behavior(creature: String, target: String, data: Dictionary) -> void:
    var key := make_pair_key(creature, target)
    _creature_behaviors[key] = data


func lookup_creature_behavior(creature: String, target: String) -> Dictionary:
    var key := make_pair_key(creature, target)
    return _creature_behaviors.get(key, {})


func ingest_spawn_data(blueprint_response: Dictionary) -> void:
    ## Bulk-load pairwise + behaviors from the backend object creation response.
    var pairwise_data: Dictionary = blueprint_response.get("pairwise", {})
    for key in pairwise_data:
        _pairwise[key] = pairwise_data[key]
    var behavior_data: Dictionary = blueprint_response.get("creature_behaviors", {})
    for key in behavior_data:
        _creature_behaviors[key] = behavior_data[key]


func invalidate_pairs_for(object_name: String) -> void:
    ## Remove stale entries when an object changes state.
    var normalized := object_name.strip_edges().to_lower()
    var stale_keys: Array = []
    for key in _pairwise:
        if normalized in key.split("::"):
            stale_keys.append(key)
    for key in stale_keys:
        _pairwise.erase(key)


func clear_scene() -> void:
    _creature_behaviors.clear()
    # Pairwise cache persists (backed by cache.db)
```

**Create `godot/scripts/data/affordance_config.gd`** — Affordance constants.

```gdscript
class_name AffordanceConfig

enum Affordance { CARRY = 0, MOUNT = 1, CLIMB = 2, NOTHING = 3 }

const CARRY_THROW_FORCE: float = 400.0
const CARRY_PICKUP_RANGE: float = 48.0
const MOUNT_DISMOUNT_OFFSET: Vector2 = Vector2(0, -32)
```

### Step 8.2 — Delete old data files and RuleEngine

**Delete these files:**
- `godot/autoloads/rule_engine.gd`
- `godot/scripts/data/substance_physics.gd`
- `godot/scripts/data/tag_contradictions.gd`
- `godot/scripts/data/tag_colors.gd`
- `godot/scripts/data/tag_animations.gd`
- `godot/scripts/data/tag_descriptions.gd`
- `godot/scripts/data/field_config.gd`
- `godot/scripts/data/behavior_display.gd`

**Modify `godot/project.godot`:**
- Remove `RuleEngine` autoload
- Add `InteractionCache="*res://scripts/data/interaction_cache.gd"` autoload (before Backend, after GameManager)

### Step 8.3 — State management (replaces tag management)

**Delete `godot/scripts/systems/tag_manager.gd`**, create **`godot/scripts/systems/state_manager.gd`**:

```gdscript
class_name StateManager
extends Node

signal state_added(state_id: int)
signal state_removed(state_id: int)
signal states_changed(states: Array)

var _states: Array = []  # Array of int (StateConfig.State values)
var _owner_name: String = ""

func get_states() -> Array:
    return _states.duplicate()

func has_state(state_id: int) -> bool:
    return state_id in _states

func add_state(state_id: int, duration: float = StateConfig.STATE_DECAY_DURATION) -> void:
    # Auto-remove contradictions
    var contradictions: Array = StateConfig.CONTRADICTIONS.get(state_id, [])
    for c in contradictions:
        if c in _states:
            remove_state(c)
    if state_id not in _states:
        _states.append(state_id)
        state_added.emit(state_id)
        states_changed.emit(_states)
    # Set up decay timer if duration > 0
    if duration > 0:
        _start_decay(state_id, duration)

func remove_state(state_id: int) -> void:
    if state_id in _states:
        _states.erase(state_id)
        _cancel_decay(state_id)
        state_removed.emit(state_id)
        states_changed.emit(_states)

# Decay timer management (same pattern as V2 TagDecay)
var _decay_timers: Dictionary = {}

func _start_decay(state_id: int, duration: float) -> void:
    _cancel_decay(state_id)
    var timer := Timer.new()
    timer.wait_time = duration
    timer.one_shot = true
    timer.timeout.connect(_on_decay_timeout.bind(state_id))
    add_child(timer)
    timer.start()
    _decay_timers[state_id] = timer

func _cancel_decay(state_id: int) -> void:
    if state_id in _decay_timers:
        var timer: Timer = _decay_timers[state_id]
        timer.stop()
        remove_child(timer)
        timer.queue_free()
        _decay_timers.erase(state_id)

func _on_decay_timeout(state_id: int) -> void:
    _decay_timers.erase(state_id)
    remove_state(state_id)
```

**Delete `godot/scripts/systems/tag_decay.gd`** — merged into StateManager above.

### Step 8.4 — Core systems rewrite

**Delete and recreate `godot/scripts/systems/collision_resolver.gd`:**

The collision resolver now looks up the pairwise cache by object name instead of matching tags to rules.

Key changes:
- `resolve_collision(body_a, body_b)` gets `.object_name` from each body
- Calls `InteractionCache.resolve_ab(name_a, name_b)` → `{pair, a_is_first}`
- If `pair` is empty: nothing happens (safe default)
- Applies effects: damage, state changes, force, destroy — directly from the pair dict
- Cascade logic preserved: depth 3, dedup by `"nameA::nameB"`, 96px radius cascade area scan
- No more `RuleEngine`, `EffectExecutor`, or `trigger_mode` filtering

**Delete and recreate `godot/scripts/systems/effect_executor.gd`:**

Dramatically simplified. No more rule-id-based dispatch. Single function:

```gdscript
static func execute_pairwise(data: Dictionary, body_a: Node, body_b: Node, a_is_first: bool) -> void:
    ## Apply effects from a pairwise cache entry.
    var target_for_a := body_a if a_is_first else body_b
    var target_for_b := body_b if a_is_first else body_a
    var damage_a: int = data.get("damage_a", 0)
    var damage_b: int = data.get("damage_b", 0)
    if damage_a > 0:
        WorldMutations.apply_damage(target_for_a, damage_a)
    if damage_b > 0:
        WorldMutations.apply_damage(target_for_b, damage_b)
    # State changes (decode 0-14)
    _apply_state_change(target_for_a, data.get("state_change_a", 0))
    _apply_state_change(target_for_b, data.get("state_change_b", 0))
    # Force on B (A gets Newton's 3rd law heuristic from engine)
    var force_b: int = data.get("force_b", 0)
    if force_b > 0:
        var dir: int = data.get("direction_b", 0)
        _apply_force(target_for_a, target_for_b, force_b, dir)
    # Destroy
    if data.get("destroy_a", false):
        WorldMutations.apply_destroy(target_for_a)
    if data.get("destroy_b", false):
        WorldMutations.apply_destroy(target_for_b)
```

**Rewrite `godot/scripts/systems/world_mutations.gd`:**

Changes:
- `apply_add_tag()` → `apply_add_state(target, state_id: int, duration: float)`
- `apply_remove_tag()` → `apply_remove_state(target, state_id: int)`
- Contradiction auto-removal uses `StateConfig.CONTRADICTIONS`
- All other methods survive with minimal changes: `apply_damage`, `apply_heal`, `apply_impulse`, `apply_dot`
- Add `apply_destroy(target)` — reduces HP to 0, triggers death

### Step 8.5 — Game object rewrite

**Rewrite `godot/scenes/game_object/game_object.gd`:**

Major changes to `init_from_blueprint(bp: Dictionary)`:
- Read V3 fields directly: `bp.get("mass", 1.0)`, `bp.get("armor", 0)`, etc.
- No more `tags`, `categories`, `compiled_behaviors`, `substance_profile`, `combat_profile`
- `object_name: String` stored for cache lookups
- `_state_manager: StateManager` replaces `_tag_manager: TagManager`
- `_armor: int` and `_indestructible: bool` stored from blueprint
- `take_damage(amount)` applies armor: `var effective = amount * (1.0 - _armor / 100.0)`
- If `autonomous`: create `CreatureBehaviorSystem` (new name for VerbBehaviorSystem replacement)
- If `has_field`: create `StateField` with `field_range` from blueprint
- `get_tags()` → returns state names as strings (compat shim for player collision)
- Remove `get_categories()`, `_reapply_physics()`
- `_affordance: int` stored for player interaction

**Rewrite `godot/scenes/game_object/physics_applicator.gd`:**

New `apply_from_v3_blueprint(bp: Dictionary)`:
- `mass = bp.get("mass", 1.0)` — direct, no substance profile lookup
- `gravity_scale = remap(bp.get("gravity", 50), 0, 100, -0.5, 2.5)` — linear map
- `friction = bp.get("friction", 30) / 100.0`
- `bounce = bp.get("bounce", 10) / 100.0`
- `linear_damp = bp.get("damping", 0.75)`
- Size from `bp.get("size_category", "medium")` via existing `PhysicsComposer` size multipliers

**Rewrite `godot/scenes/game_object/object_visual.gd`:**

Two visual categories:

State-based (replaces tag-based):
- All `TagAnimations` refs → `StateConfig` refs
- `refresh_tag_visuals(tags)` → `refresh_state_visuals(states: Array)`
- Particles, shaders, color shifts keyed by `StateConfig.State` instead of tag strings

Physics-derived (new, set once at creation):
- `gravity < 25` → bobbing (was FLYING tag)
- `autonomous == true` → breathing (was LIVING tag)
- `bounce > 60` → squash/stretch on collision (was BOUNCY tag)

Dropped visuals: swaying (WIND_SOURCE), alpha pulse (GLOWING), jitter (EXPLOSIVE/BRITTLE)

### Step 8.6 — Field and creature behavior

**Delete `godot/scripts/systems/tag_field.gd`**, create **`godot/scripts/systems/state_field.gd`:**

- Created when `has_field == true`
- `field_range` from blueprint (cm → pixels)
- Area2D at that radius
- Periodic timer (2s): for each overlapping body, look up `InteractionCache.lookup_pairwise(owner_name, body_name)`. If `mode == 1` (continuous): apply effects every tick. If `mode == 0` (instant): apply once on enter.
- Invalidation: when owner gains/loses a state, `InteractionCache.invalidate_pairs_for(owner_name)` — stale entries re-evaluated lazily from backend

**Delete `godot/scripts/systems/verb_behavior_system.gd`**, create **`godot/scripts/systems/creature_behavior.gd`:**

Per-pair behavior system. Reads behavior data from `InteractionCache.lookup_creature_behavior()`.

Per-frame logic — utility scoring:
```gdscript
func _physics_process(delta):
    var best_utility := -1.0
    var best_target: Node = null
    var best_data: Dictionary = {}

    for pair in _pair_data:
        if pair.movement == 3:  # ignore
            continue
        var dist := _owner.global_position.distance_to(pair.target.global_position)
        var utility := pair.strength / (1.0 + dist / _perception_range)
        if pair.movement == 1:  # flee
            utility *= 1.5
        if utility > best_utility:
            best_utility = utility
            best_target = pair.target
            best_data = pair

    if best_target == null:
        return

    match best_data.movement:
        0:  # approach
            _move_toward(best_target, delta)
            if _at_contact_range(best_target):
                _execute_arrival_action(best_target, best_data)
        1:  # flee
            _move_away_from(best_target, delta)
        2:  # orbit
            _orbit_around(best_target, delta)
            if _at_orbit_range(best_target):
                _execute_arrival_action(best_target, best_data)
```

On-arrival actions map to same engine primitives as pairwise outcomes: damage, heal, add_state, remove_state, destroy, take.

### Step 8.7 — Backend autoload, UI, environment bodies, levels

**Rewrite `godot/autoloads/backend.gd`:**
- `create_session()`: remove `RuleEngine.load_rules(rules)` — no rules to load
- `create_object()`: after receiving blueprint, call `InteractionCache.ingest_spawn_data(response)` to populate pairwise + creature behavior data
- Delete `fetch_rules()` entirely
- Remove `_etag` variable
- All other methods unchanged (WebSocket, sprite delivery, sync, session persistence)

**Rewrite `godot/scenes/environment_body/environment_body.gd`:**

Per migration.md Option A — env bodies are named objects in the pairwise cache:
- `init_env(id, env_name, size, color, solid)` — takes a name for cache lookups
- `env_name: String` stored as identity
- `get_object_name() -> String` returns `env_name`
- Tags replaced by states: `_state_manager: StateManager`
- Periodic tick: `InteractionCache.lookup_pairwise(env_name, body_name)` for each overlapping body
- Solidity: `State.FROZEN in _state_manager.get_states()` instead of `"FROZEN" in tags`

**Rewrite `godot/scripts/ui/debug_label.gd`:**
- State badges (colored by `StateConfig.COLORS`) instead of tag badges
- Physics line: `m=%.1f g=%d f=%d b=%d a=%d`
- Affordance indicator

**Rewrite `godot/scenes/hud/object_creation_panel.gd`:**
- Remove tag badges section
- Add physics display (mass, gravity, bounce, friction, armor, hp)
- Add affordance indicator
- Remove behavior section

**Update `godot/autoloads/event_bus.gd`:**
- `object_tags_changed` signal → `object_states_changed`

**Update `godot/scenes/levels/base_level.gd`:**
- `_create_env_body()` takes `env_name: String` instead of `env_tags: Array`
- `_seed_interactions()` method to pre-populate InteractionCache for level seed objects

**Update level files** (level_01.gd, level_02.gd, level_03.gd):
- Convert seed object blueprints to V3 format (physics values instead of substance/tags)
- Convert env body calls to use names instead of tags
- Add `_seed_interactions()` with hardcoded pairwise data for seed object + env body pairs

**Update `godot/scenes/player/player.gd`:**
- `get_object_name() -> String` returns `"player"` (for pairwise cache lookups)
- `get_tags()` returns `["LIVING"]` (compat shim, minimal change)
- Remove `get_categories()`
- `_push_rigid_bodies()`: check `body.blueprint.get("mass", 1.0) < 0.5` instead of HEAVY tag

### Validation

- Godot editor opens without errors
- Create session works (no rules download errors)
- Create object shows V3Blueprint data in creation panel
- Collision between two objects looks up pairwise cache
- Environment body periodic tick applies effects from pairwise cache
- Debug labels show states and physics values

---

## Phase 9 — Eval system, tests, cleanup

**Why:** Verify the V3 pipeline produces reasonable results. Update test infrastructure. Clean up dead references.

This phase has internal parallelism: eval work and test work are independent.

### Eval changes

**Delete these eval metrics:**
- `backend/evals/metrics/substance_accuracy.py`
- `backend/evals/metrics/element_accuracy.py`
- `backend/evals/metrics/category_accuracy.py`
- `backend/evals/metrics/tag_recall.py`
- `backend/evals/metrics/interaction_surface.py`

**Rewrite `backend/evals/metrics/validity.py`:**

V3 schema validation. Checks: mass in [0.001, 100000], height in [1, 5000], friction/bounce/gravity in [0, 100], armor/hp in [0, 100], indestructible is bool, has_field is bool (if true, field_range in [1, 5000]), autonomous is bool, affordance in [0, 3], visual_description length >= 40, name is 1-3 words.

**Create `backend/evals/metrics/physics_reasonableness.py`:**

Deterministic. Pattern-matching rules for known archetypes:
- "sword"/"blade": mass 0.5-5kg, height 60-150cm
- "boulder"/"mountain": mass > 100, gravity > 50
- "feather"/"balloon": mass < 0.1, gravity < 30
- "fire"/"flame": mass < 1
- General: all values in valid ranges

Score = passed_rules / applicable_rules.

**Create `backend/evals/metrics/affordance_accuracy.py`:**

Checks affordance against expected value from metadata. Score 1.0 if match or no expectation.

**Create `backend/evals/metrics/autonomous_accuracy.py`:**

Checks autonomous flag against expected. Creatures should be true, items false.

**Rewrite LLM judge rubrics** in `backend/evals/metrics/__init__.py`:
- **Faithfulness**: physics properties + affordance + visual match player intent
- **Delight**: physics invite experimentation
- **Visual Clarity**: remove substance/tag consistency check

**Modify `backend/evals/models.py`:**

Add `V3ParsedOutput` (mass, height, friction, bounce, gravity, armor, hp, indestructible, has_field, field_range, autonomous, affordance, visual_description), `V3CaseResult`, `V3EvalRunResult` (version=3).

**Create `backend/evals/v3_dataset.yaml`:**

Reuse the 90 case descriptions. New metadata:
```yaml
- name: fire sword
  inputs: fire sword
  metadata:
    category: weapon
    expected_mass_range: [0.5, 5.0]
    expected_affordance: 0
    expected_autonomous: false
```

**Modify `backend/evals/run_eval.py`:**

Add `--v3` flag. When set: load v3_dataset.yaml, use V3 evaluators, save V3EvalRunResult.

### New backend tests

| File | What it tests |
|------|--------------|
| `backend/tests/test_v3_blueprint.py` | V3Blueprint validation, height_to_size_category, damping derivation |
| `backend/tests/test_states.py` | State enum, contradictions, decode_state_change round-trip |
| `backend/tests/test_cache.py` | CacheManager CRUD, key normalization, pair key symmetry |
| `backend/tests/test_creation_graph.py` | Question list completeness, format kwargs, fan-out/fan-in assembly (mocked LLM) |
| `backend/tests/test_pairwise.py` | Screening, 9-call evaluation, sorted key convention, resolver (mocked LLM) |
| `backend/tests/test_creature_behavior.py` | 3-stage evaluation, filtering, scene context (mocked LLM) |

**Modify existing tests:**
- `test_api_objects.py` — V3 blueprint format
- `test_session_manager.py` — V3Blueprint serialization
- `test_config.py` — Cache settings
- `test_cli.py` — V3 CLI output

### Cleanup

**Grep for dead references** across entire codebase:
```
RuleEngine, TagManager, TagDecay, TagField, TagColors, TagAnimations,
TagDescriptions, TagContradictions, FieldConfig, SubstancePhysics,
BehaviorDisplay, VerbBehaviorSystem, substance_profile, combat_profile,
compiled_behaviors, tags_required_a, tags_required_b, derive_traits,
resolve_profile, compute_combat_profile, CreatorOutput, GameObjectBlueprint,
Substance, Element, BehaviorVerb, InteractionRule, RuleResolver
```

Remove any remaining references.

**Update `CLAUDE.md`** — Add note at top: "V3 architecture. See docs/v3-design/ for design docs." Don't do a full rewrite until V3 is validated — CLAUDE.md describes running code, not planned code.

**Update `docs/v3-design/index.md`** — Add implementation-plan.md to the doc table.

### Validation

```bash
make check    # lint + typecheck + test all pass
make cli-create PROMPT="fire sword"   # V3Blueprint JSON
make cli-sprite PROMPT="fire sword"   # sprite generated
# Godot: open editor, play level 1, create an object, verify collision resolution
```

---

## File operation summary

| Phase | Create | Delete | Modify |
|-------|--------|--------|--------|
| 0 | 3 fixture YAMLs | — | — |
| 1 | — | 11 backend + 5 tests | 6 stubs |
| 2 | 4 models | — | 1 (session.py) |
| 3 | 4 cache files | — | 1 (config.py) |
| 4 | 3 llm files | — | 1 (config.py) |
| 5 | 1 (creator/create.py) | — | 5 (objects.py, main.py, sessions/manager.py, pipeline.py, cli.py) |
| 6 | 4 engine files | — | 1 (objects.py) |
| 7 | 1 (engine/behavior.py) | — | 1 (engine/spawn.py) |
| 8 | 5 GDScript + rewrites of ~12 | 10 GDScript | ~10 GDScript |
| 9 | 6 tests + 3 eval metrics + 1 dataset | 5 eval metrics | ~8 eval/test files |

**Total: ~30 files created, ~31 files deleted, ~35 files modified.**
