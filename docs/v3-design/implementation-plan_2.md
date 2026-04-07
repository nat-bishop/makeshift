# V3 Implementation Plan

## Context

V2 uses hand-authored substances (16), tags (31), elements (7), categories (7), behavior verbs (6), and 56 rules to drive object physics and interactions. V3 replaces all of this with LLM-generated physics (parallel 1-token questions) and a pairwise interaction cache (LLM-evaluated at spawn time, looked up at runtime). The goal: unlimited emergent interactions without manual rule authoring, shippable on consumer hardware via small-model decomposition.

This plan is ordered by dependency graph. Each phase builds on the previous and ends with a concrete validation step.

---

## Phase 0 — Extract V2 Ground Truth

Before any code changes, extract data from V2 files that will be deleted later. This data becomes eval fixtures for validating V3 quality.

### 0A. Extract interaction pairs from rules

**File:** `backend/evals/fixtures/v2_interaction_pairs.json` (CREATE)

Read `backend/app/engine/rules_data.py` (56 `InteractionRule` instances in `ALL_RULES`). For each rule, extract:

```json
[
  {
    "rule_id": "heat_flammable_ignite",
    "tags_a": ["HEAT_SOURCE"],
    "tags_b": ["FLAMMABLE"],
    "expected_effects": [
      {"type": "DAMAGE", "target": "b"},
      {"type": "ADD_TAG", "target": "b", "tag": "HEAT_SOURCE"}
    ],
    "description": "Fire ignites flammable objects"
  }
]
```

This is ground truth for pairwise cache quality: "does the LLM produce similar outcomes to what a human game designer authored?"

### 0B. Extract substance physics reference

**File:** `backend/evals/fixtures/v2_substance_physics.json` (CREATE)

Read `backend/app/models/substances.py`. Extract `SUBSTANCE_PROFILES` dict. For each substance:

```json
{
  "metal": {"mass": 8.0, "durability": 200, "friction": 0.4, "burn_rate": 0.0, "state": "solid"},
  "wood": {"mass": 2.0, "durability": 100, "friction": 0.6, "burn_rate": 0.8, "state": "solid"},
  "water": {"mass": 1.0, "durability": 50, "friction": 0.1, "state": "liquid"},
  "fire": {"mass": 0.1, "durability": 30, "friction": 0.0, "state": "energy"}
}
```

This calibrates physics reasonableness checks: "does `mass_kg` for a metal sword fall near 1-8kg?"

### 0C. Validation

```bash
python -c "import json; d=json.load(open('backend/evals/fixtures/v2_interaction_pairs.json')); print(f'{len(d)} rules extracted')"
python -c "import json; d=json.load(open('backend/evals/fixtures/v2_substance_physics.json')); print(f'{len(d)} substances extracted')"
```

Both files parse. Rule count = 56. Substance count = 16.

---

## Phase 1 — Backend Data Layer

New data models and cache system. No LLM calls yet. Everything else depends on these shapes.

### 1A. States model

**File:** `backend/app/models/states.py` (CREATE)

```python
from enum import StrEnum

class State(StrEnum):
    ON_FIRE = "on_fire"
    FROZEN = "frozen"
    WET = "wet"
    ELECTRIFIED = "electrified"
    POISONED = "poisoned"
    CORRODED = "corroded"
    MOLTEN = "molten"

# Directed: adding key removes all values
STATE_CONTRADICTIONS: dict[State, list[State]] = {
    State.ON_FIRE: [State.FROZEN, State.WET],
    State.FROZEN: [State.ON_FIRE, State.MOLTEN],
    State.WET: [State.ON_FIRE],
    State.MOLTEN: [State.FROZEN],
}

# For LLM prompt encoding: state_id 1-7 = add, 8-14 = remove
STATE_BY_ID: dict[int, State] = {i + 1: s for i, s in enumerate(State)}

def decode_state_change(code: int) -> tuple[str, State] | None:
    """Decode 0-14 integer to (action, state) or None.
    0 = no change. 1-7 = add state. 8-14 = remove state."""
    if code == 0:
        return None
    if 1 <= code <= 7:
        return ("add", STATE_BY_ID[code])
    if 8 <= code <= 14:
        return ("remove", STATE_BY_ID[code - 7])
    return None
```

### 1B. V3 Blueprint model

**File:** `backend/app/models/blueprint.py` (REWRITE)

Delete: `CreatorOutput`, `BehaviorVerb`, `BehaviorVerbSpec`, all V2 validators, all imports of `Substance`, `Element`, `Tag`, `Category`, `BEHAVIOR_TARGETS`, `LLM_VISIBLE_TAGS`.

Keep: `VisualDescriptor` (unchanged — `visual_description: str` + `size_category: Literal[...]`).

New `GameObjectBlueprint`:

```python
from pydantic import BaseModel, Field
from typing import Literal

class VisualDescriptor(BaseModel):
    visual_description: str = Field(description="1-2 sentences for sprite gen")
    size_category: Literal["tiny", "small", "medium", "large", "huge"] = "medium"

class GameObjectBlueprint(BaseModel):
    id: str
    name: str
    description: str  # original player input

    # Physics (from LLM, cached)
    mass_kg: float = Field(ge=0.001, le=100000)
    height_cm: int = Field(ge=1, le=5000)
    friction: int = Field(ge=0, le=100)     # 0=ice, 90=rubber
    bounce: int = Field(ge=0, le=100)       # 0=clay, 99=super ball
    gravity: int = Field(ge=0, le=100)      # 0=floats, 50=normal, 75=anvil

    # Destructibility
    armor: int = Field(ge=0, le=100)        # damage reduction %
    hp: int = Field(ge=0, le=100)           # 0=skip → indestructible
    indestructible: bool = False

    # Field
    has_field: bool = False
    field_range_cm: int = Field(default=0, ge=0, le=5000)

    # Classification
    autonomous: bool = False                # is a creature
    affordance: int = Field(default=3, ge=0, le=3)  # 0=carry, 1=mount, 2=climb, 3=nothing

    # Visual
    visual_descriptor: VisualDescriptor

    # Runtime state (not from LLM — starts empty, modified by interactions)
    states: list[str] = Field(default_factory=list)
```

Note: `states` field defaults empty. Objects are born stateless. States are added by interactions at runtime.

Damping is derived, not LLM-decided: `damping = height_cm / (mass_kg * 100 + 10)`. Compute this in the Godot physics applicator or in a helper, not stored in the blueprint.

### 1C. Pairwise result model

**File:** `backend/app/models/pairwise.py` (CREATE)

```python
from pydantic import BaseModel

class PairwiseResult(BaseModel):
    """Cached outcome of two objects interacting."""
    damage_a: int = 0          # 0-100
    damage_b: int = 0          # 0-100
    state_change_a: int = 0    # 0-14 encoding (0=none, 1-7=add, 8-14=remove)
    state_change_b: int = 0    # 0-14 encoding
    force_b: int = 0           # 0-100
    direction_b: int = 0       # 0=push, 1=pull
    destroy_a: bool = False
    destroy_b: bool = False
    mode: int = 0              # 0=instant, 1=continuous
```

### 1D. Cache manager

**File:** `backend/app/cache/__init__.py` (CREATE, empty)
**File:** `backend/app/cache/manager.py` (CREATE)

```python
import aiosqlite
import json
import re

class CacheManager:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @staticmethod
    def normalize_key(name: str) -> str:
        """Lowercase, strip, collapse internal whitespace."""
        return re.sub(r'\s+', ' ', name.strip().lower())

    @staticmethod
    def pair_key(name_a: str, name_b: str) -> str:
        """Sorted pair key: 'fire sword::wooden shield'."""
        a = CacheManager.normalize_key(name_a)
        b = CacheManager.normalize_key(name_b)
        return f"{min(a,b)}::{max(a,b)}"

    async def get(self, cache_type: str, key: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT value_json FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def set(self, cache_type: str, key: str, value: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO cache (cache_type, cache_key, value_json, model_version, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (cache_type, key, json.dumps(value), "", __import__('time').time()),
        )
        await self._db.commit()

    async def exists(self, cache_type: str, key: str) -> bool:
        cursor = await self._db.execute(
            "SELECT 1 FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        return await cursor.fetchone() is not None
```

### 1E. Config + DB initialization

**File:** `backend/app/config.py` (MODIFY)

Add one field to `Settings`:
```python
cache_database_path: str = "data/cache.db"
```

**File:** `backend/app/main.py` (MODIFY)

In `lifespan()`, after game.db setup, add cache.db initialization:

```python
cache_db = await aiosqlite.connect(settings.cache_database_path)
await cache_db.execute("""
    CREATE TABLE IF NOT EXISTS cache (
        cache_type TEXT NOT NULL,
        cache_key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        model_version TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (cache_type, cache_key)
    )
""")
await cache_db.commit()
app.state.cache_db = cache_db
```

Add `await cache_db.close()` in the shutdown section.

Remove: `from app.creator.agent import _get_agent` and the `_get_agent()` warm-up call.
Remove: `from app.routers import rules` and `app.include_router(rules.router)`.

### 1F. Session model update

**File:** `backend/app/models/session.py` (MODIFY)

`WorldObject.blueprint` type changes from `GameObjectBlueprint` (old) to `GameObjectBlueprint` (new). No structural change needed — just ensure imports point to the rewritten blueprint.py.

**File:** `backend/app/sessions/manager.py` (MODIFY)

The `get_session()` method deserializes `blueprint_json` via `GameObjectBlueprint.model_validate_json()`. This will work with the new schema. Old sessions with V2 blueprints will fail to deserialize — this is acceptable (wipe `game.db` for V3 dev).

### 1G. Validation

```bash
cd backend && uv run python -c "
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.states import State, decode_state_change, STATE_CONTRADICTIONS
from app.models.pairwise import PairwiseResult

# Blueprint roundtrip
bp = GameObjectBlueprint(
    id='test', name='fire sword', description='fire sword',
    mass_kg=1.5, height_cm=120, friction=30, bounce=10, gravity=50,
    armor=80, hp=90, indestructible=False,
    has_field=True, field_range_cm=150,
    autonomous=False, affordance=0,
    visual_descriptor=VisualDescriptor(visual_description='a flaming sword', size_category='small')
)
j = bp.model_dump_json()
bp2 = GameObjectBlueprint.model_validate_json(j)
assert bp2.mass_kg == 1.5
assert bp2.states == []

# State encoding
assert decode_state_change(0) is None
assert decode_state_change(1) == ('add', State.ON_FIRE)
assert decode_state_change(8) == ('remove', State.ON_FIRE)

# Pairwise roundtrip
pr = PairwiseResult(damage_a=0, damage_b=40, state_change_b=1, force_b=20)
assert pr.model_dump()['state_change_b'] == 1

print('Phase 1 data layer OK')
"
```

---

## Phase 2 — Backend Creation Pipeline + Pairwise Evaluator

Replace the single PydanticAI agent call with parallel 1-token LLM questions. Add pairwise interaction evaluation.

### 2A. Question definitions

**File:** `backend/app/creator/questions.py` (CREATE)

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class Question:
    key: str
    prompt_template: str  # {name} is substituted
    max_tokens: int
    parse: Callable[[str], int | float | bool | str]

def parse_int(s: str) -> int:
    """Extract first integer from LLM output."""
    import re
    m = re.search(r'\d+', s.strip())
    return int(m.group()) if m else 0

def parse_float(s: str) -> float:
    import re
    m = re.search(r'[\d.]+', s.strip())
    return float(m.group()) if m else 1.0

def parse_bool(s: str) -> bool:
    return s.strip().startswith('1')

def parse_text(s: str) -> str:
    return s.strip()

CREATION_QUESTIONS: list[Question] = [
    Question("mass_kg",
        "How heavy is {name} in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500, house=50000). Reply with just the number.",
        4, parse_float),
    Question("height_cm",
        "How tall/long is {name} in cm? (ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800). Reply with just the number.",
        2, parse_int),
    Question("friction",
        "How grippy is {name} 0-100? (ice=0, metal=30, wood=50, rubber=90). Reply with just the number.",
        1, parse_int),
    Question("bounce",
        "How bouncy is {name} 0-100? (clay=0, wood=20, tennis ball=70, super ball=99). Reply with just the number.",
        1, parse_int),
    Question("gravity",
        "Gravity pull on {name} 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75). Reply with just the number.",
        1, parse_int),
    Question("armor",
        "How resistant to damage is {name} 0-100? (paper=5, wood=30, steel=80, diamond=99). Reply with just the number.",
        1, parse_int),
    Question("hp",
        "How much punishment can {name} take before destroyed 0-100? (balloon=5, wood=40, steel=80). Reply 0 if indestructible. Reply with just the number.",
        1, parse_int),
    Question("indestructible",
        "Can {name} be destroyed? 0=yes it can be destroyed, 1=no it is indestructible. Reply with just 0 or 1.",
        1, parse_bool),
    Question("has_field",
        "Does {name} affect nearby things without touching them (heat, magnetism, wind, radiation)? 0=no 1=yes. Reply with just 0 or 1.",
        1, parse_bool),
    Question("field_range_cm",
        "If {name} affects nearby things, what range in cm? (candle=50, campfire=250, bonfire=500, volcano=1000). Reply 0 if no field. Reply with just the number.",
        2, parse_int),
    Question("autonomous",
        "Is {name} a living creature that moves on its own? 0=no 1=yes. Reply with just 0 or 1.",
        1, parse_bool),
    Question("affordance",
        "When a player interacts with {name}: 0=carry it, 1=ride/mount it, 2=climb it, 3=nothing/no interaction. Reply with just the number.",
        1, parse_int),
]

# Visual description is a separate question — more output tokens, runs in parallel with the rest
VISUAL_QUESTION = Question("visual_description",
    "Describe {name} for a 2D game sprite artist in 1-2 sentences. Focus on shape, material, colors, distinctive features. Describe only the object, not a scene.",
    60, parse_text)
```

### 2B. Creation pipeline

**File:** `backend/app/creator/pipeline.py` (CREATE)

```python
import asyncio
import uuid
import structlog
from pydantic_ai import Agent
from app.cache.manager import CacheManager
from app.config import settings
from app.creator.questions import CREATION_QUESTIONS, VISUAL_QUESTION, Question
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor

logger = structlog.get_logger()

# Reuse _build_model() from the existing agent.py to construct the LLM model
# Copy _build_model() into this file or extract to a shared module

async def _ask(question: Question, name: str) -> tuple[str, any]:
    """Ask one question, return (key, parsed_value)."""
    prompt = question.prompt_template.format(name=name)
    # Use PydanticAI Agent with output_type=str for simplicity
    agent = Agent(
        _build_model(),
        output_type=str,
        model_settings={"max_tokens": question.max_tokens, "temperature": 0.3},
    )
    result = await agent.run(prompt)
    parsed = question.parse(result.output)
    return (question.key, parsed)

async def create_object(description: str, cache: CacheManager) -> GameObjectBlueprint:
    """V3 creation pipeline: check cache, fan-out parallel questions, assemble blueprint."""
    name = description.strip()
    cache_key = CacheManager.normalize_key(name)

    # Check creation cache
    cached = await cache.get("creation", cache_key)
    if cached:
        logger.info("creation_cache_hit", name=name)
        return GameObjectBlueprint(**cached, id=str(uuid.uuid4()), description=description)

    # Fan-out: all property questions + visual question in parallel
    all_questions = CREATION_QUESTIONS + [VISUAL_QUESTION]
    results = await asyncio.gather(
        *[_ask(q, name) for q in all_questions],
        return_exceptions=True,
    )

    # Assemble results dict, handling failures
    props = {}
    for i, r in enumerate(results):
        q = all_questions[i]
        if isinstance(r, Exception):
            logger.warning("question_failed", key=q.key, error=str(r))
            # Use sensible defaults
            props[q.key] = 0 if q.key != "visual_description" else f"a {name}"
        else:
            props[q.key] = r[1]

    # Clamp values
    props["mass_kg"] = max(0.001, min(100000, props.get("mass_kg", 1.0)))
    props["height_cm"] = max(1, min(5000, props.get("height_cm", 50)))
    for k in ("friction", "bounce", "gravity", "armor", "hp"):
        props[k] = max(0, min(100, props.get(k, 50)))
    props["field_range_cm"] = max(0, min(5000, props.get("field_range_cm", 0)))
    props["affordance"] = max(0, min(3, props.get("affordance", 3)))
    if not props.get("has_field"):
        props["field_range_cm"] = 0

    # Determine size_category from height_cm
    h = props["height_cm"]
    if h <= 5: size_cat = "tiny"
    elif h <= 40: size_cat = "small"
    elif h <= 150: size_cat = "medium"
    elif h <= 400: size_cat = "large"
    else: size_cat = "huge"

    blueprint_data = {
        "name": name,
        "mass_kg": props["mass_kg"],
        "height_cm": props["height_cm"],
        "friction": props["friction"],
        "bounce": props["bounce"],
        "gravity": props["gravity"],
        "armor": props["armor"],
        "hp": props["hp"],
        "indestructible": bool(props.get("indestructible", False)),
        "has_field": bool(props.get("has_field", False)),
        "field_range_cm": props["field_range_cm"],
        "autonomous": bool(props.get("autonomous", False)),
        "affordance": props["affordance"],
        "visual_descriptor": {
            "visual_description": props.get("visual_description", f"a {name}"),
            "size_category": size_cat,
        },
    }

    # Write to creation cache
    await cache.set("creation", cache_key, blueprint_data)

    return GameObjectBlueprint(
        id=str(uuid.uuid4()),
        description=description,
        **blueprint_data,
    )
```

Extract `_build_model()` from `backend/app/creator/agent.py` into a shared utility `backend/app/creator/llm.py` (CREATE) so both the old agent (kept temporarily) and new pipeline can use it. The function builds a PydanticAI model from config (local SGLang or cloud).

### 2C. Pairwise evaluator

**File:** `backend/app/engine/pairwise.py` (CREATE)

```python
import asyncio
import structlog
from app.cache.manager import CacheManager
from app.models.pairwise import PairwiseResult

logger = structlog.get_logger()

def _obj_summary(bp: dict) -> str:
    """One-line object summary for LLM prompts."""
    parts = [f"{bp['name']}: {bp['mass_kg']}kg, armor {bp['armor']}, hp {bp['hp']}"]
    if bp.get("has_field"):
        parts.append(f"field {bp['field_range_cm']}cm")
    if bp.get("states"):
        parts.append(f"[{', '.join(bp['states'])}]")
    return ", ".join(parts)

SCREENING_PROMPT = """New object: {new_summary}.
Scene objects:
{scene_list}
Which scene objects would interact interestingly with {new_name}? List their numbers separated by commas. If none, reply "none"."""

PAIRWISE_QUESTIONS = [
    ("damage_a",        "[{a}] collides with [{b}]. Damage to {a_name}? 0-100. Reply with just the number."),
    ("damage_b",        "[{a}] collides with [{b}]. Damage to {b_name}? 0-100. Reply with just the number."),
    ("state_change_a",  "[{a}] collides with [{b}]. State change on {a_name}? 0=none, 1=add on_fire, 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded, 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet, 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten. Reply with just the number."),
    ("state_change_b",  "[{a}] collides with [{b}]. State change on {b_name}? 0=none, 1=add on_fire, 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded, 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet, 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten. Reply with just the number."),
    ("force_b",         "[{a}] collides with [{b}]. How much force pushes {b_name}? 0-100 (0=none, 30=nudge, 70=strong push, 100=explosion). Reply with just the number."),
    ("direction_b",     "[{a}] collides with [{b}]. Does {a_name} push or pull {b_name}? 0=push 1=pull. Reply with just 0 or 1."),
    ("destroy_a",       "[{a}] collides with [{b}]. Is {a_name} destroyed by this collision? 0=no 1=yes. Reply with just 0 or 1."),
    ("destroy_b",       "[{a}] collides with [{b}]. Is {b_name} destroyed by this collision? 0=no 1=yes. Reply with just 0 or 1."),
    ("mode",            "[{a}] collides with [{b}]. Is the interaction instant or continuous? 0=instant (single hit) 1=continuous (ongoing while touching). Reply with just 0 or 1."),
]

async def screen_pairs(new_bp: dict, scene_bps: list[dict], cache: CacheManager) -> list[int]:
    """Return indices of scene objects that interact interestingly with new_bp."""
    # ... screening call implementation
    # Returns list of 0-based indices into scene_bps

async def evaluate_pair(bp_a: dict, bp_b: dict, cache: CacheManager) -> PairwiseResult:
    """Evaluate one pair with 9 parallel 1-token calls. Cache the result."""
    pair_key = CacheManager.pair_key(bp_a["name"], bp_b["name"])

    # Check cache
    cached = await cache.get("pairwise", pair_key)
    if cached:
        return PairwiseResult(**cached)

    # Determine lexicographic A/B order
    a_name, b_name = sorted([bp_a["name"], bp_b["name"]])
    a_bp = bp_a if bp_a["name"] == a_name else bp_b
    b_bp = bp_b if bp_b["name"] == b_name else bp_a
    a_summary = _obj_summary(a_bp)
    b_summary = _obj_summary(b_bp)

    # Fan-out 9 questions
    # ... parallel LLM calls, parse results, assemble PairwiseResult

    # Write to cache
    result = PairwiseResult(...)
    await cache.set("pairwise", pair_key, result.model_dump())
    return result

async def evaluate_new_object(new_bp: dict, scene_bps: list[dict], cache: CacheManager) -> None:
    """Screen + evaluate all interesting pairs for a new object entering the scene."""
    interesting_indices = await screen_pairs(new_bp, scene_bps, cache)
    await asyncio.gather(*[
        evaluate_pair(new_bp, scene_bps[i], cache)
        for i in interesting_indices
    ])
```

### 2D. V3 resolver (cache-backed)

**File:** `backend/app/engine/resolver.py` (REWRITE)

Delete: `RuleResolver` class, all tag-pair indexing logic.

New content:

```python
from app.cache.manager import CacheManager
from app.models.pairwise import PairwiseResult

class V3Resolver:
    def __init__(self, cache: CacheManager):
        self._cache = cache

    async def resolve(self, name_a: str, name_b: str) -> PairwiseResult | None:
        """Look up cached pairwise result. Returns None if uncached (fallback: nothing happens)."""
        pair_key = CacheManager.pair_key(name_a, name_b)
        data = await self._cache.get("pairwise", pair_key)
        if data is None:
            return None
        return PairwiseResult(**data)
```

### 2E. Router updates

**File:** `backend/app/routers/objects.py` (MODIFY)

- Change `from app.creator.agent import create_object` to `from app.creator.pipeline import create_object`
- Pass `cache` (from `request.app.state.cache_db` → `CacheManager`) to `create_object()`
- After blueprint creation, schedule pairwise evaluation as a background task:
  ```python
  # Fetch all other object blueprints in this session
  session = await manager.get_session(session_id)
  scene_bps = [obj.blueprint.model_dump() for obj in session.objects if obj.object_id != blueprint.id]
  # Schedule pairwise eval
  task2 = asyncio.create_task(evaluate_new_object(blueprint.model_dump(), scene_bps, cache))
  _background_tasks.add(task2)
  task2.add_done_callback(_background_tasks.discard)
  ```

**File:** `backend/app/routers/rules.py` (DELETE)

No longer needed. V3 has no static rules to download.

**File:** `backend/app/routers/sessions.py` (MODIFY)

Remove `_RULES_JSON`, `_RULES_ETAG`, and all rules-related logic from session create/restore responses.

**File:** `backend/app/routers/pairwise.py` (CREATE)

New endpoint for Godot to fetch pairwise results:

```python
@router.get("/scene/{session_id}")
async def get_scene_pairwise(session_id: str, request: Request) -> dict:
    """Return all cached pairwise results for objects in this session."""
    # Load session objects, compute all pair keys, batch-fetch from cache
    # Return dict of {pair_key: PairwiseResult}
```

### 2F. CLI update

**File:** `backend/app/cli.py` (MODIFY)

Update `cli-create` command to use the new pipeline. The CLI needs to open cache.db itself since there's no running FastAPI app.

### 2G. Validation

```bash
make cli-create PROMPT="fire sword"
# Should output V3 blueprint JSON with mass_kg, height_cm, friction, etc.
# Run twice — second call should show "creation_cache_hit" in logs

make cli-create PROMPT="wooden shield"
# Should produce different physics than fire sword
```

---

## Phase 3 — Godot Core: Blueprint + Pairwise Interactions

Make the Godot client read V3 blueprints and use pairwise cache for collision resolution.

### 3A. Physics applicator — direct blueprint reads

**File:** `godot/scenes/game_object/physics_applicator.gd` (REWRITE)

Replace `SubstancePhysics.resolve_physics()` and `apply_tag_modifiers()` with direct blueprint reads:

```gdscript
func apply_from_blueprint(bp: Dictionary) -> void:
    var mass_kg: float = bp.get("mass_kg", 1.0)
    var friction_pct: int = bp.get("friction", 50)
    var bounce_pct: int = bp.get("bounce", 0)
    var gravity_pct: int = bp.get("gravity", 50)
    var height_cm: int = bp.get("height_cm", 50)

    # Damping derived: light large things (feather) = high, heavy small (bullet) = low
    var damping: float = float(height_cm) / (mass_kg * 100.0 + 10.0)
    damping = clampf(damping, 0.0, 10.0)

    # Gravity scale: 0-100 → -1.0 to 2.0
    # 0→-1.0 (floats up), 50→1.0 (normal), 100→2.0 (heavy pull)
    var gravity_scale: float = (gravity_pct - 50.0) / 25.0  # 0→-2, 50→0, 100→2
    # Actually: let's use a simpler mapping: 0→-0.5, 25→0.25, 50→1.0, 75→1.5, 100→2.0
    gravity_scale = lerpf(-0.5, 2.0, gravity_pct / 100.0)

    var size_cat: String = bp.get("visual_descriptor", {}).get("size_category", "medium")
    var size_data: Dictionary = PhysicsComposer.get_size_data(size_cat)
    var mass_mult: float = PhysicsComposer.get_size_mass_multiplier(size_cat)

    apply_physics({
        "mass": mass_kg * mass_mult,
        "gravity": gravity_scale,
        "friction": friction_pct / 100.0,
        "bounce": bounce_pct / 100.0,
        "damping": damping,
    }, size_cat)
```

No more SubstancePhysics dependency. No more tag modifiers at runtime (V3 has no creation-time tags — physics are fixed at creation, only states change at runtime, and states don't modify physics).

### 3B. Game object — V3 blueprint init

**File:** `godot/scenes/game_object/game_object.gd` (MODIFY)

Changes to `init_from_blueprint()`:
- Remove: `_tag_manager` creation, `_tag_manager.init_tags(bp.get("tags", []))`, tag signal connections
- Remove: `_categories` parsing, `add_to_group("living")` based on tags
- Remove: `compiled_behaviors` handling, `VerbBehaviorSystem` creation (deferred to Phase 5)
- Remove: `FieldConfig.has_any_field_tag(tags)` check (deferred to Phase 4)
- Add: `var _states: Array = []`
- Add: `var _autonomous: bool = false` read from `bp.get("autonomous", false)`
- Add: If autonomous, `add_to_group("living")`
- Keep: `physics_applicator.apply_from_blueprint(bp)`, `object_visual.set_object_id()`, debug label, `_emit_entered_scene()`

Replace `get_tags() -> Array[String]` with `get_states() -> Array` (returns `_states`). Keep `get_tags()` as alias returning `_states` for backward compat during transition.

Replace `add_tag()`/`remove_tag()` with `add_state(state)`/`remove_state(state)`. These modify `_states` directly (state_manager added in Phase 4).

`_reapply_physics()` — remove entirely. V3 physics are fixed at creation. States don't modify physics. (If states should modify physics later, add it back with state-specific modifiers.)

`_on_body_entered()` — keep, still defers to CollisionResolver.

### 3C. Backend autoload — pairwise cache

**File:** `godot/autoloads/backend.gd` (MODIFY)

- Remove: `fetch_rules()` method, `RuleEngine.load_rules()` calls
- Add: `var _pairwise_cache: Dictionary = {}` (in-memory, key = "name_a::name_b")
- Add: `func get_pairwise(name_a: String, name_b: String) -> Dictionary` — normalizes and sorts names, looks up in `_pairwise_cache`, returns empty dict if miss
- Add: `func fetch_scene_pairwise(session_id: String)` — calls `GET /api/pairwise/scene/{session_id}`, populates `_pairwise_cache`
- Add: Handle WebSocket message `{"type": "pairwise_ready", "pair_key": "...", "result": {...}}` to update `_pairwise_cache` as background evals complete
- Call `fetch_scene_pairwise()` on session create/restore (replaces `fetch_rules()`)

### 3D. Collision resolver — cache lookup

**File:** `godot/scripts/systems/collision_resolver.gd` (MODIFY)

Replace `RuleEngine.find_matching_rules(tags_a, tags_b)` with:

```gdscript
func resolve_and_notify(body_a: Node, body_b: Node, cascade_depth: int = 0,
        trigger_mode_filter: String = "", resolved: Dictionary = {}) -> void:
    var name_a: String = body_a.blueprint.get("name", "")
    var name_b: String = body_b.blueprint.get("name", "")
    var pair_result: Dictionary = Backend.get_pairwise(name_a, name_b)
    if pair_result.is_empty():
        return  # uncached = nothing happens (safe default)

    # Determine which body is A and which is B (lexicographic sort)
    var sorted_names: Array = [name_a, name_b]
    sorted_names.sort()
    var a_body: Node = body_a if name_a == sorted_names[0] else body_b
    var b_body: Node = body_b if name_b == sorted_names[1] else body_a

    EffectExecutor.execute_pairwise(pair_result, a_body, b_body)
```

Cascade logic stays similar but triggers on state changes from pairwise results instead of tag-change checks.

### 3E. Effect executor — V3 outcomes

**File:** `godot/scripts/systems/effect_executor.gd` (MODIFY)

Add new method:

```gdscript
func execute_pairwise(result: Dictionary, body_a: Node, body_b: Node) -> void:
    # Damage
    if result.get("damage_a", 0) > 0:
        WorldMutations.apply_damage(body_a, result["damage_a"])
    if result.get("damage_b", 0) > 0:
        WorldMutations.apply_damage(body_b, result["damage_b"])

    # State changes (0-14 encoding)
    _apply_state_change(result.get("state_change_a", 0), body_a)
    _apply_state_change(result.get("state_change_b", 0), body_b)

    # Force on B (force on A derived: Newton's 3rd law)
    if result.get("force_b", 0) > 0:
        var direction: Vector2 = (body_b.global_position - body_a.global_position).normalized()
        if result.get("direction_b", 0) == 1:  # pull
            direction = -direction
        WorldMutations.apply_impulse(body_b, direction, result["force_b"] * 5.0)
        # Reciprocal force on A
        var mass_ratio: float = body_b.mass / max(body_a.mass, 0.01)
        WorldMutations.apply_impulse(body_a, -direction, result["force_b"] * 5.0 * mass_ratio)

    # Destroy
    if result.get("destroy_a", false):
        body_a.take_damage(99999)
    if result.get("destroy_b", false):
        body_b.take_damage(99999)

func _apply_state_change(code: int, body: Node) -> void:
    if code == 0:
        return
    # 1-7 = add state, 8-14 = remove state
    var states := ["on_fire", "frozen", "wet", "electrified", "poisoned", "corroded", "molten"]
    if code >= 1 and code <= 7:
        body.add_state(states[code - 1])
    elif code >= 8 and code <= 14:
        body.remove_state(states[code - 8])
```

### 3F. WebSocket — pairwise delivery

**File:** `backend/app/ws/handler.py` (MODIFY)

Add `send_pairwise_ready(session_id, pair_key, result_dict)` function. Called by pairwise evaluator when a pair completes. Godot receives this and updates its in-memory cache.

### 3G. Delete/stub V2 remnants

- `godot/autoloads/rule_engine.gd` — Delete the file. Remove from Godot project autoloads (in `project.godot`).
- `godot/scripts/data/substance_physics.gd` — Delete. No longer imported.
- `backend/app/routers/rules.py` — Already deleted in 2E.

### 3H. Validation

```
make api  # start backend
# In a separate terminal:
make play  # launch Godot
# In game: create "fire sword", create "wooden shield"
# Observe: fire sword has reasonable physics (mass ~1.5kg, bounces a little)
# Collide fire sword with wooden shield
# Observe: pairwise interaction fires (damage to shield, maybe on_fire state)
```

---

## Phase 4 — State System

Runtime state management on Godot side. States are added/removed by pairwise interactions and decay over time.

### 4A. State contradictions

**File:** `godot/scripts/data/state_contradictions.gd` (CREATE, replaces `tag_contradictions.gd`)

```gdscript
class_name StateContradictions

# Adding key removes all values
const CONTRADICTIONS: Dictionary = {
    "on_fire": ["frozen", "wet"],
    "frozen": ["on_fire", "molten"],
    "wet": ["on_fire"],
    "molten": ["frozen"],
}

static func get_contradictions(state: String) -> Array:
    return CONTRADICTIONS.get(state, [])
```

### 4B. State manager

**File:** `godot/scripts/systems/state_manager.gd` (CREATE, replaces `tag_manager.gd`)

Same structure as TagManager but with 7-state vocabulary. Signals: `state_added(state)`, `state_removed(state)`, `states_changed(states)`. On `add_state()`, auto-remove contradictions via `StateContradictions.get_contradictions()`.

### 4C. State decay

**File:** `godot/scripts/systems/state_decay.gd` (MODIFY — rename references from "tag" to "state")

Minimal change: `remove_tag()` calls become `remove_state()` on parent.

### 4D. State colors

**File:** `godot/scripts/data/state_colors.gd` (CREATE, replaces `tag_colors.gd`)

```gdscript
class_name StateColors

const COLORS: Dictionary = {
    "on_fire": Color(1.0, 0.5, 0.0),      # orange
    "frozen": Color(0.5, 0.8, 1.0),        # ice blue
    "wet": Color(0.3, 0.5, 0.8),           # water blue
    "electrified": Color(1.0, 1.0, 0.3),   # yellow
    "poisoned": Color(0.3, 0.8, 0.3),      # green
    "corroded": Color(0.6, 0.4, 0.2),      # brown
    "molten": Color(1.0, 0.3, 0.0),        # red-orange
}
const HEAL: Color = Color(0.3, 1.0, 0.3)

static func get_color(state: String) -> Color:
    return COLORS.get(state, Color.WHITE)

static func is_stateful(body: Node) -> bool:
    return body.has_method("get_states")
```

### 4E. Field system

**File:** `godot/scripts/systems/field_system.gd` (CREATE, replaces `tag_field.gd`)

Simplified: reads `has_field` and `field_range_cm` directly from blueprint (no FieldConfig lookup). Creates Area2D with blueprint-specified radius. Periodic tick (2s) routes through CollisionResolver using the same pairwise cache lookup. No separate continuous vs periodic distinction — all field interactions use the pairwise cache.

```gdscript
func init_field(owner: Node, bp: Dictionary) -> void:
    _owner = owner
    if not bp.get("has_field", false):
        return
    var range_cm: int = bp.get("field_range_cm", 100)
    var range_px: float = range_cm * 0.5  # cm → pixels conversion factor
    _create_area(range_px)
    _start_periodic_timer()  # 2s interval
```

### 4F. Wire state system into game_object.gd

**File:** `godot/scenes/game_object/game_object.gd` (MODIFY)

- Create `StateManager` child in `init_from_blueprint()`
- Wire `state_added`/`state_removed`/`states_changed` signals
- Create field system if `bp.get("has_field", false)`
- `add_state()` / `remove_state()` delegate to StateManager
- `_on_states_changed()` → refresh visuals, emit `EventBus.object_tags_changed` (keep signal name for now or rename)

### 4G. World mutations update

**File:** `godot/scripts/systems/world_mutations.gd` (MODIFY)

- `apply_add_tag()` → `apply_add_state()`: use `StateContradictions` instead of `TagContradictions`
- `apply_remove_tag()` → `apply_remove_state()`

### 4H. Delete V2 tag files

- `godot/scripts/systems/tag_manager.gd` — DELETE
- `godot/scripts/data/tag_contradictions.gd` — DELETE
- `godot/scripts/systems/tag_field.gd` — DELETE
- `godot/scripts/data/field_config.gd` — DELETE
- `godot/scripts/data/tag_descriptions.gd` — DELETE

### 4I. Validation

```
# Create fire sword + wooden shield, collide them
# Shield should gain "on_fire" state
# Create bucket of water, collide with on_fire shield
# on_fire should be removed
# Wait 10s — state should decay if no re-application
# Add "frozen" to an on_fire object — on_fire auto-removed (contradiction)
```

---

## Phase 5 — Creature Behavior + Visuals

### 5A. Creature behavior evaluator (backend)

**File:** `backend/app/engine/creature_behavior.py` (CREATE)

3-stage sequential evaluation. Per-scene, in-memory only (not in cache.db).

```python
# Stage 1+1b (parallel, all creature×object pairs):
#   Movement: "Scene: [...]. {creature} sees {object}. 0=approach 1=flee 2=orbit 3=ignore"
#   Strength: "How strongly does {creature} react to {object}? 0-100"
#
# Filter: keep pairs where movement != ignore (3)
#
# Stage 2 (parallel, approaching/orbiting pairs only):
#   Action: "{creature} is APPROACHING {object}. On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take"
#
# Stage 3 (parallel, actions needing params):
#   For damage/heal: "Amount? 0-100"
#   For add/remove state: "Which state? 1-7" (same state encoding)

@dataclass
class CreatureBehavior:
    target_name: str
    movement: int      # 0=approach, 1=flee, 2=orbit, 3=ignore
    strength: int      # 0-100
    action: int        # 0-7 (only for approach/orbit)
    action_param: int  # damage amount, state id, etc.

async def evaluate_creature_behaviors(
    creature_bp: dict,
    scene_bps: list[dict],
    scene_inventory: list[str],
) -> list[CreatureBehavior]:
    """Evaluate one creature against all scene objects. Returns list of behaviors."""
```

### 5B. Creature behavior endpoint

**File:** `backend/app/routers/objects.py` (MODIFY)

When a new autonomous object is created, trigger creature behavior eval. When a new non-autonomous object is created, trigger re-eval for existing autonomous objects. Deliver results via WebSocket message `{"type": "creature_behaviors", "creature_id": "...", "behaviors": [...]}`.

### 5C. Verb behavior system — V3 rewrite

**File:** `godot/scripts/systems/verb_behavior_system.gd` (REWRITE)

Replace fixed-verb system with per-pair behavior from backend data.

```gdscript
# Receives behaviors as array of dicts from backend:
# [{target_name: "donut", movement: 0, strength: 90, action: 5, action_param: 0}, ...]

var _behaviors: Array = []
var _perception_range: float = 400.0  # pixels

func init_behaviors(behaviors: Array, owner: Node) -> void:
    _owner = owner
    _behaviors = behaviors
    # Subscribe to EventBus for target tracking

func _physics_process(delta: float) -> void:
    if _behaviors.is_empty():
        return
    var best_target: Node = null
    var best_utility: float = -1.0
    var best_behavior: Dictionary = {}

    for behavior in _behaviors:
        var target := _find_target_by_name(behavior["target_name"])
        if target == null:
            continue
        var dist: float = _owner.global_position.distance_to(target.global_position)
        var utility: float = behavior["strength"] / (1.0 + dist / _perception_range)
        if behavior["movement"] == 1:  # flee
            utility *= 1.5  # survival bias
        if utility > best_utility:
            best_utility = utility
            best_target = target
            best_behavior = behavior

    if best_target == null:
        return

    # Execute movement
    match best_behavior["movement"]:
        0: _approach(best_target)
        1: _flee_from(best_target)
        2: _orbit(best_target)

    # Execute on-arrival action (when close enough)
    if best_behavior["movement"] == 0:  # approach
        var dist: float = _owner.global_position.distance_to(best_target.global_position)
        if dist < MELEE_RANGE:
            _execute_action(best_behavior, best_target)
```

### 5D. State visuals

**File:** `godot/scripts/data/state_visuals.gd` (CREATE, replaces `tag_animations.gd`)

Map 7 states to visual effects:

```gdscript
class_name StateVisuals

const STATE_PARTICLES: Dictionary = {
    "on_fire": {color = Color(1, 0.5, 0), direction = Vector2.UP, amount = 12},
    "wet": {color = Color(0.3, 0.5, 0.8), direction = Vector2.DOWN, amount = 6},
    "electrified": {color = Color(1, 1, 0.3), direction = Vector2(0, 0), amount = 8},  # burst
    "poisoned": {color = Color(0.3, 0.8, 0.3), direction = Vector2.UP, amount = 6},
    "corroded": {color = Color(0.6, 0.4, 0.2), direction = Vector2.DOWN, amount = 4},
    "molten": {color = Color(1, 0.3, 0), direction = Vector2.UP, amount = 10},
}

const STATE_SHADERS: Dictionary = {
    "frozen": "res://shaders/ice.gdshader",    # new shader needed
    "molten": "res://shaders/ripple.gdshader",  # existing
}

const STATE_COLOR_SHIFTS: Dictionary = {
    "frozen": Color(0.5, 0.8, 1.0),
    "poisoned": Color(0.3, 0.8, 0.3),
    "corroded": Color(0.6, 0.4, 0.2),
}

const STATE_LIGHTS: Dictionary = {
    "on_fire": {color = Color(1, 0.6, 0.2), energy = 0.8, range = 64},
    "molten": {color = Color(1, 0.4, 0.1), energy = 0.5, range = 48},
}
```

### 5E. Object visual — physics-derived animations

**File:** `godot/scenes/game_object/object_visual.gd` (MODIFY)

Replace tag-keyed animation lookup with:

```gdscript
func init_from_blueprint(bp: Dictionary) -> void:
    # Physics-derived animations (replace FLYING/LIVING/BOUNCY tag triggers)
    if bp.get("gravity", 50) < 25:
        _add_animation("bobbing", {amplitude = 3.0, speed = 2.0})
    if bp.get("autonomous", false):
        _add_animation("breathing", {amplitude = 0.03, speed = 1.5})
    # bounce > 60 enables squash/stretch on collision (checked in _on_collision)

func refresh_state_visuals(states: Array) -> void:
    # State-keyed visuals (replace tag-keyed)
    _clear_state_effects()
    for state in states:
        if state in StateVisuals.STATE_PARTICLES:
            _add_particles(state)
        if state in StateVisuals.STATE_SHADERS:
            _apply_shader(StateVisuals.STATE_SHADERS[state])
        if state in StateVisuals.STATE_COLOR_SHIFTS:
            _apply_color_shift(StateVisuals.STATE_COLOR_SHIFTS[state])
        if state in StateVisuals.STATE_LIGHTS:
            _add_light(StateVisuals.STATE_LIGHTS[state])
```

### 5F. Delete V2 visual/behavior files

- `godot/scripts/data/tag_animations.gd` — DELETE
- `godot/scripts/data/tag_colors.gd` — DELETE
- `godot/scripts/data/behavior_display.gd` — DELETE

### 5G. Validation

```
# Create "zombie cop" — should be autonomous
# Create "donut" — zombie should approach it
# Create "campfire" — zombie should flee from fire (if fire has field)
# Observe: zombie breathes (autonomous=true)
# Observe: campfire bobs (gravity < 25 since fire/smoke floats)
# Observe: fire sword has on_fire particles when states applied
```

---

## Phase 6 — Affordances + Environment Bodies + Cleanup

### 6A. Affordance system (Godot)

**File:** `godot/scripts/systems/affordance_system.gd` (CREATE)

New interaction system. Player presses interact near an object → check `blueprint.affordance`:

- **0 (carry):** Reparent object under player's hand Marker2D. Object freeze = true. Player can swing (arc tween, check overlaps, apply held object's pairwise interactions). Throw = reparent to scene, unfreeze, apply impulse.
- **1 (mount):** Player reparents under object. Object physics govern movement. Player input steers.
- **2 (climb):** While player overlaps, player gains upward velocity.
- **3 (nothing):** No interaction.

Wire into player script: on interact input, find nearest object with affordance 0/1/2 within range, execute.

### 6B. Environment bodies → named GameObjects

**Design decision: Option A** — environment bodies are named objects in the pairwise cache.

**File:** `godot/scenes/environment_body/environment_body.gd` (REWRITE)

Environment bodies become indestructible GameObjects with:
- Pre-registered creation cache entries (level designer specifies name: "acid pool", "lava pit", etc.)
- Pairwise interactions evaluated at level load against all seed objects
- No sprite gen (use level-defined ColorRect)
- `indestructible = true`, `hp = 0`

Level scripts provide env body definitions as V3-format blueprint dicts:

```gdscript
func _create_env_body(pos: Vector2, size: Vector2, name: String, color: Color, solid: bool) -> Node:
    # Blueprint is fetched from creation cache or pre-defined
    var bp: Dictionary = {
        "id": name + "_" + str(pos),
        "name": name,
        "description": name,
        "mass_kg": 99999, "height_cm": int(size.y), "friction": 50,
        "bounce": 0, "gravity": 50, "armor": 100, "hp": 0,
        "indestructible": true, "has_field": true,
        "field_range_cm": int(size.x * 0.6),
        "autonomous": false, "affordance": 3,
        "visual_descriptor": {"visual_description": name, "size_category": "large"},
        "states": [],
    }
    # ... instantiate StaticBody2D, init from blueprint
```

At level load, the backend evaluates pairwise interactions between env bodies and seed objects. These are pre-cached in cache.db for shipped levels.

### 6C. Backend V2 cleanup — DELETE

These files are fully replaced by V3 code and should be deleted:

| File | Reason |
|------|--------|
| `backend/app/models/substances.py` | 16 substances → LLM-generated physics |
| `backend/app/models/tags.py` | 31 tags → 7 states |
| `backend/app/models/tag_behaviors.py` | `resolve_implied_behaviors()` → creature behavior evaluator |
| `backend/app/models/rules.py` | `InteractionRule` → pairwise cache |
| `backend/app/models/effects.py` | `EffectType` enum → pairwise result fields |
| `backend/app/engine/rules_data.py` | 56 rules → pairwise cache |
| `backend/app/engine/trait_deriver.py` | `derive_traits()`/`resolve_profile()`/`compute_combat_profile()` → direct LLM physics |
| `backend/app/creator/agent.py` | PydanticAI agent → parallel question pipeline |

### 6D. Godot V2 cleanup — DELETE

| File | Reason |
|------|--------|
| `godot/scripts/data/substance_physics.gd` | Deleted in Phase 3 |
| `godot/scripts/data/field_config.gd` | Deleted in Phase 4 |
| `godot/scripts/data/tag_animations.gd` | Deleted in Phase 5 |
| `godot/scripts/data/tag_colors.gd` | Deleted in Phase 5 |
| `godot/scripts/data/tag_contradictions.gd` | Deleted in Phase 4 |
| `godot/scripts/data/tag_descriptions.gd` | Deleted in Phase 4 |
| `godot/scripts/data/behavior_display.gd` | Deleted in Phase 5 |
| `godot/autoloads/rule_engine.gd` | Deleted in Phase 3 |

### 6E. Docs and config cleanup

- `CLAUDE.md` — Rewrite to describe V3 architecture. Don't do this until V3 code is working.
- Archive V2 docs to `docs/archive/`: `ARCHITECTURE.md`, `GAME_DESIGN.md`, `action-plan.md`
- Keep: `LEVEL_DESIGN.md` (update for V3), `scribblenauts-deep-dive.md`, `llm-behavior-systems.md`, `ANIMATION_PIPELINE.md`

### 6F. Validation (full game loop)

```
make dev
# 1. Create "fire sword" — correct physics, sprite generates
# 2. Create "wooden shield" — pairwise eval runs in background
# 3. Collide fire sword with shield — damage + on_fire state
# 4. Create "bucket of water" — pairwise eval against both objects
# 5. Collide water with on_fire shield — on_fire removed, water may be destroyed
# 6. Create "zombie cop" — autonomous, creature behavior eval runs
# 7. Create "donut" — zombie approaches donut, eats it
# 8. Pick up fire sword (carry affordance) — reparent under player
# 9. Swing fire sword at zombie — held object's pairwise interaction fires
# 10. Environment acid pool damages objects that touch it via pairwise cache
```

---

## Open Design Decisions — Resolutions

### Environment bodies: Option A (named objects in pairwise cache)

Env bodies participate in the same pairwise cache as player-created objects. The LLM naturally answers "acid pool hits wooden bridge → damage 40, add corroded." This is the cleanest V3 answer — no special cases. Level pre-warming (ship seeded cache.db) eliminates first-load latency. Env bodies are initialized with hand-crafted blueprint dicts at level design time (mass, armor, etc. are known), but their pairwise interactions are LLM-evaluated.

### Eval system: Rebuild incrementally

Phase 0 extracts V2 ground truth. V3 evals are a separate effort after the core loop works. New metrics:
- **Physics reasonableness:** mass/friction/bounce/gravity within expected ranges for known objects (calibrate against V2 substance physics)
- **Pairwise quality:** fire+wood→damage+on_fire (calibrate against V2 rules as ground truth)
- **Creature behavior:** zombie+donut→approach+eat (manual test cases)
- Keep: **Visual Clarity** (LLM judge), **Has Signature** (visual_description quality)
- Delete: Substance Accuracy, Element Accuracy, Category Accuracy, Tag Recall, Interaction Surface

### Visual triggers: Physics-derived + state-keyed

No creation-time tags in V3. Physics values and the autonomous flag drive creation-time visuals. States drive runtime visuals. Mapping:
- `gravity < 25` → bobbing (was FLYING tag)
- `autonomous == true` → breathing (was LIVING tag)
- `bounce > 60` → squash/stretch on collision (was BOUNCY tag)
- States (on_fire, frozen, etc.) → particles, shaders, color shifts (replaces tag visuals)
- Dropped: swaying (WIND_SOURCE), alpha pulse (GLOWING), jitter (EXPLOSIVE/BRITTLE) — no V3 equivalent, can revisit

### Pairwise state invalidation: Lazy re-eval with safe fallback

When an object gains/loses a state, mark affected pairwise cache entries as stale. On next collision with a stale pair, use the base (non-stale) result as immediate fallback while re-evaluation runs async (~145ms). This avoids blocking gameplay. The stale pair is re-evaluated with active states included in the prompt.

---

## Risk Mitigation

1. **LLM answer quality** (HIGH) — Test creation pipeline against V2 substance physics early. If 1-token answers are unreliable, consider constrained decoding (regex parameter in SGLang) or fall back to structured output.

2. **Pairwise cache consistency** (HIGH) — Same pair must produce same results. Creation cache handles this for physics. Pairwise cache keyed by normalized sorted names. State-dependent re-evaluation is the edge case — test thoroughly.

3. **Godot breaking during transition** (MEDIUM) — V2 code assumes tags everywhere. Phases 3-4 are the riskiest because game_object.gd, collision_resolver.gd, and effect_executor.gd all change simultaneously. Mitigation: do Phase 3 as one atomic commit that keeps the game bootable.

4. **Session migration** (LOW) — Old game.db sessions won't deserialize with new blueprint schema. Resolution: wipe game.db. Cache.db is new and starts empty.
