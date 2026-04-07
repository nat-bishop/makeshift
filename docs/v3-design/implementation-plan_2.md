# V3 Implementation Plan

## Context

V2 uses hand-authored substances (16), tags (31), elements (7), categories (7), behavior verbs (6), and 56 rules to drive object physics and interactions. V3 replaces all of this with LLM-generated physics (parallel 1-token questions) and a pairwise interaction cache (LLM-evaluated at spawn time, looked up at runtime). The goal: unlimited emergent interactions without manual rule authoring, shippable on consumer hardware via small-model decomposition.

---

## Dependency Graph

```
Phase 0: Extract V2 Ground Truth
    |
Phase 1: Data Contract (shared models, JSON wire format, cache schema)
    |
    +---------------------------+
    |                           |
  BACKEND TRACK             CLIENT TRACK
    |                           |
  B1: Creation Pipeline       C1: State System + Physics
    |                           |
  B2: LLM Quality Gate       C2: Collision + Effects
    |                           |
  B3: Pairwise + Resolver    C3: State Visuals +
    |                             Physics Animations
  B4: Creature Behavior +
      Destruction Cache
    |                           |
    +---------------------------+
    |
Phase INT: Integration (wire backend ↔ client)
    |
Phase 5: Creature Behavior (Godot)
    |
Phase 6: Affordances (carry / mount / climb)
    |
Phase 7: Environment Bodies + Cleanup
```

After Phase 1 establishes the data contract, backend and client tracks have **no dependencies on each other** until integration. They can progress in parallel — backend builds the full LLM pipeline while client adapts its data layer and collision flow to the new format using mock/hardcoded test data.

---

## JSON Wire Format

These are the exact JSON shapes that flow between backend and Godot. Both sides must agree on these before any implementation.

### V3 Blueprint (HTTP response from `POST /api/sessions/{id}/objects`, also stored in `objects.blueprint_json`)

```json
{
  "id": "uuid-string",
  "name": "fire sword",
  "description": "fire sword",
  "mass_kg": 1.5,
  "height_cm": 120,
  "friction": 30,
  "bounce": 10,
  "gravity": 50,
  "armor": 80,
  "hp": 90,
  "indestructible": false,
  "has_field": true,
  "field_range_cm": 150,
  "autonomous": false,
  "affordance": 0,
  "visual_descriptor": {
    "visual_description": "a flaming steel longsword with ember particles",
    "size_category": "small"
  },
  "states": [],
  "destruction_result_name": "broken sword blade"
}
```

### Pairwise Result (WebSocket `pairwise_ready` message, also returned by `GET /api/pairwise/scene/{session_id}`)

```json
{
  "type": "pairwise_ready",
  "pair_key": "fire sword::wooden shield",
  "result": {
    "damage_a": 0,
    "damage_b": 40,
    "state_change_a": 0,
    "state_change_b": 1,
    "force_b": 20,
    "direction_b": 0,
    "destroy_a": false,
    "destroy_b": false,
    "mode": 0
  }
}
```

State change encoding: `0`=none, `1-7`=add state (on_fire, frozen, wet, electrified, poisoned, corroded, molten), `8-14`=remove same states. `mode`: `0`=instant, `1`=continuous. `direction_b`: `0`=push, `1`=pull. Force on A is engine-derived (Newton's 3rd law heuristic), not in the wire format.

### Creature Behavior (WebSocket `creature_behaviors` message)

```json
{
  "type": "creature_behaviors",
  "creature_id": "uuid-string",
  "behaviors": [
    {
      "target_name": "donut",
      "movement": 0,
      "strength": 90,
      "action": 5,
      "action_param": 0
    },
    {
      "target_name": "campfire",
      "movement": 1,
      "strength": 70,
      "action": 0,
      "action_param": 0
    }
  ]
}
```

Movement: `0`=approach, `1`=flee, `2`=orbit, `3`=ignore. Action: `0`=nothing, `1`=damage, `2`=heal, `3`=add state, `4`=remove state, `5`=destroy, `6`=take. `action_param`: damage/heal amount (0-100) for actions 1-2, state_id (1-7) for actions 3-4, unused for 0/5/6.

### Creature Re-evaluation Request (WebSocket client→server)

```json
{
  "type": "reevaluate_creature",
  "creature_id": "uuid-string",
  "reason": "state_change"
}
```

Backend re-runs creature behavior evaluation and sends updated `creature_behaviors` message.

---

## Phase 0 — Extract V2 Ground Truth

Before any code changes, extract data from V2 files that will be deleted later.

### 0A. Interaction pairs

**File:** `backend/evals/fixtures/v2_interaction_pairs.json` (CREATE)

Read `backend/app/engine/rules_data.py` (56 `InteractionRule` instances in `ALL_RULES`). Extract each rule:

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

### 0B. Substance physics reference

**File:** `backend/evals/fixtures/v2_substance_physics.json` (CREATE)

Read `backend/app/models/substances.py`. Extract `SUBSTANCE_PROFILES`:

```json
{
  "metal": {"mass": 8.0, "durability": 200, "friction": 0.4, "burn_rate": 0.0, "state": "solid"},
  "wood": {"mass": 2.0, "durability": 100, "friction": 0.6, "burn_rate": 0.8, "state": "solid"},
  "water": {"mass": 1.0, "durability": 50, "friction": 0.1, "state": "liquid"},
  "fire": {"mass": 0.1, "durability": 30, "friction": 0.0, "state": "energy"}
}
```

### 0C. Creature behavior fixtures

**File:** `backend/evals/fixtures/v2_creature_behaviors.yaml` (CREATE)

Hand-authored ground truth for creature behavior quality testing. ~20 entries:

```yaml
- creature: zombie
  target: brain
  expected_movement: approach
  expected_action: destroy
  notes: classic zombie behavior

- creature: firefighter
  target: burning tree
  expected_movement: approach
  expected_action: remove_state
  expected_param: on_fire

- creature: firefighter
  target: trapped person
  expected_movement: approach
  expected_action: heal

- creature: cat
  target: mouse
  expected_movement: approach
  expected_action: destroy

- creature: cat
  target: dog
  expected_movement: flee

- creature: cat
  target: ball of yarn
  expected_movement: orbit
  expected_action: nothing

- creature: guard dog
  target: burglar
  expected_movement: approach
  expected_action: damage

- creature: guard dog
  target: owner
  expected_movement: orbit
  expected_action: nothing
  notes: protective orbiting

- creature: vampire
  target: garlic
  expected_movement: flee

- creature: vampire
  target: human
  expected_movement: approach
  expected_action: damage

- creature: rabbit
  target: carrot
  expected_movement: approach
  expected_action: destroy
  notes: eating

- creature: rabbit
  target: wolf
  expected_movement: flee

- creature: zombie cop
  target: donut
  expected_movement: approach
  expected_action: destroy
  notes: eats it

- creature: zombie cop
  target: criminal
  expected_movement: approach
  expected_action: damage

- creature: doctor
  target: injured person
  expected_movement: approach
  expected_action: heal

- creature: bee
  target: flower
  expected_movement: approach
  expected_action: nothing
  notes: pollinating

- creature: bee
  target: bear
  expected_movement: approach
  expected_action: damage
  notes: defensive stinging

- creature: dragon
  target: knight
  expected_movement: approach
  expected_action: damage

- creature: dragon
  target: gold coin
  expected_movement: approach
  expected_action: take
```

### 0D. Validation

```bash
python -c "import json; d=json.load(open('backend/evals/fixtures/v2_interaction_pairs.json')); print(f'{len(d)} rules extracted')"
python -c "import json; d=json.load(open('backend/evals/fixtures/v2_substance_physics.json')); print(f'{len(d)} substances extracted')"
python -c "import yaml; d=yaml.safe_load(open('backend/evals/fixtures/v2_creature_behaviors.yaml')); print(f'{len(d)} creature behaviors extracted')"
```

### 0E. Test file

**File:** `backend/tests/test_fixtures.py` (CREATE)

```python
"""Validate V2 ground truth fixtures are parseable and non-empty."""
import json
from pathlib import Path
import yaml

FIXTURE_DIR = Path(__file__).parent.parent / "evals" / "fixtures"

def test_interaction_pairs():
    data = json.loads((FIXTURE_DIR / "v2_interaction_pairs.json").read_text())
    assert len(data) == 56
    assert all("rule_id" in r for r in data)

def test_substance_physics():
    data = json.loads((FIXTURE_DIR / "v2_substance_physics.json").read_text())
    assert len(data) == 16
    assert "metal" in data

def test_creature_behaviors():
    data = yaml.safe_load((FIXTURE_DIR / "v2_creature_behaviors.yaml").read_text())
    assert len(data) >= 15
    assert all("creature" in e and "target" in e for e in data)
```

---

## Phase 1 — Data Contract

Shared models, cache schema, and config. Both tracks depend on this, nothing else depends on each other.

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

# Directed: adding key auto-removes all values
STATE_CONTRADICTIONS: dict[State, list[State]] = {
    State.ON_FIRE: [State.FROZEN, State.WET],
    State.FROZEN: [State.ON_FIRE, State.MOLTEN],
    State.WET: [State.ON_FIRE],
    State.MOLTEN: [State.FROZEN],
}

# For LLM prompt encoding: state_id 1-7 maps to states in enum order
STATE_BY_ID: dict[int, State] = {i + 1: s for i, s in enumerate(State)}

def decode_state_change(code: int) -> tuple[str, State] | None:
    """Decode 0-14 to (action, state) or None.
    0=none, 1-7=add state, 8-14=remove state."""
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

Delete: `CreatorOutput`, `BehaviorVerb`, `BehaviorVerbSpec`, all validators, all imports of `Substance`, `Element`, `Tag`, `Category`, `BEHAVIOR_TARGETS`, `LLM_VISIBLE_TAGS`.

Keep: `VisualDescriptor` (unchanged).

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

    # Physics (LLM-generated, cached by name)
    mass_kg: float = Field(ge=0.001, le=100000)
    height_cm: int = Field(ge=1, le=5000)
    friction: int = Field(ge=0, le=100)
    bounce: int = Field(ge=0, le=100)
    gravity: int = Field(ge=0, le=100)

    # Destructibility
    armor: int = Field(ge=0, le=100)
    hp: int = Field(ge=0, le=100)
    indestructible: bool = False

    # Field
    has_field: bool = False
    field_range_cm: int = Field(default=0, ge=0, le=5000)

    # Classification
    autonomous: bool = False
    affordance: int = Field(default=3, ge=0, le=3)  # 0=carry, 1=mount, 2=climb, 3=nothing

    # Visual
    visual_descriptor: VisualDescriptor

    # Destruction
    destruction_result_name: str = ""  # e.g. "pile of charred splinters"

    # Runtime (starts empty, modified by interactions)
    states: list[str] = Field(default_factory=list)
```

### 1C. Pairwise result model

**File:** `backend/app/models/pairwise.py` (CREATE)

```python
from pydantic import BaseModel

class PairwiseResult(BaseModel):
    damage_a: int = 0
    damage_b: int = 0
    state_change_a: int = 0  # 0-14
    state_change_b: int = 0  # 0-14
    force_b: int = 0
    direction_b: int = 0     # 0=push, 1=pull
    destroy_a: bool = False
    destroy_b: bool = False
    mode: int = 0             # 0=instant, 1=continuous
```

### 1D. Cache manager

**File:** `backend/app/cache/__init__.py` (CREATE, empty)
**File:** `backend/app/cache/manager.py` (CREATE)

```python
import json, re, time
import aiosqlite

class CacheManager:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @staticmethod
    def normalize_key(name: str) -> str:
        return re.sub(r'\s+', ' ', name.strip().lower())

    @staticmethod
    def pair_key(name_a: str, name_b: str) -> str:
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
            (cache_type, key, json.dumps(value), "", time.time()),
        )
        await self._db.commit()

    async def exists(self, cache_type: str, key: str) -> bool:
        cursor = await self._db.execute(
            "SELECT 1 FROM cache WHERE cache_type = ? AND cache_key = ?",
            (cache_type, key),
        )
        return await cursor.fetchone() is not None

    async def get_by_prefix(self, cache_type: str, prefix: str) -> dict[str, dict]:
        """Return all entries whose key starts with prefix. For bulk scene loading."""
        cursor = await self._db.execute(
            "SELECT cache_key, value_json FROM cache WHERE cache_type = ? AND cache_key LIKE ?",
            (cache_type, f"{prefix}%"),
        )
        return {row[0]: json.loads(row[1]) async for row in cursor}

    async def get_all_for_names(self, cache_type: str, names: list[str]) -> dict[str, dict]:
        """Return all pairwise entries involving any of the given names."""
        results = {}
        for i, a in enumerate(names):
            for b in names[i+1:]:
                key = self.pair_key(a, b)
                data = await self.get(cache_type, key)
                if data:
                    results[key] = data
        return results
```

Four cache types: `creation`, `pairwise`, `creature_behavior` (scene-local, in-memory only — NOT persisted to cache.db), `destruction_result`.

### 1E. Config + DB init

**File:** `backend/app/config.py` (MODIFY)

Add to `Settings`:
```python
cache_database_path: str = "data/cache.db"
```

**File:** `backend/app/main.py` (MODIFY)

In `lifespan()`, after game.db setup:

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

Add `await cache_db.close()` in shutdown. Remove `from app.creator.agent import _get_agent` and `_get_agent()` warm-up. Remove `from app.routers import rules` and `app.include_router(rules.router)`.

### 1F. Test file

**File:** `backend/tests/test_data_contract.py` (CREATE)

```python
"""Phase 1: data contract tests."""
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor
from app.models.states import State, decode_state_change, STATE_CONTRADICTIONS
from app.models.pairwise import PairwiseResult
from app.cache.manager import CacheManager

def test_blueprint_roundtrip():
    bp = GameObjectBlueprint(
        id="test", name="fire sword", description="fire sword",
        mass_kg=1.5, height_cm=120, friction=30, bounce=10, gravity=50,
        armor=80, hp=90, indestructible=False,
        has_field=True, field_range_cm=150,
        autonomous=False, affordance=0,
        visual_descriptor=VisualDescriptor(visual_description="a flaming sword", size_category="small"),
        destruction_result_name="broken sword blade",
    )
    j = bp.model_dump_json()
    bp2 = GameObjectBlueprint.model_validate_json(j)
    assert bp2.mass_kg == 1.5
    assert bp2.states == []
    assert bp2.destruction_result_name == "broken sword blade"

def test_blueprint_empty_states():
    bp = GameObjectBlueprint(
        id="t", name="rock", description="rock",
        mass_kg=5.0, height_cm=30, friction=50, bounce=5, gravity=60,
        armor=70, hp=80, indestructible=False,
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
    await db.execute("""CREATE TABLE cache (
        cache_type TEXT NOT NULL, cache_key TEXT NOT NULL,
        value_json TEXT NOT NULL, model_version TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (cache_type, cache_key))""")
    cache = CacheManager(db)
    assert await cache.get("creation", "fire sword") is None
    await cache.set("creation", "fire sword", {"mass_kg": 1.5})
    result = await cache.get("creation", "fire sword")
    assert result["mass_kg"] == 1.5
    assert await cache.exists("creation", "fire sword")
    await db.close()
```

### 1G. Validation

```bash
make test  # new tests pass alongside existing tests that don't import deleted V2 models
```

Note: some existing tests import V2 models (substances, tags, rules). Those will break — mark them as expected failures or delete them. The V2 ground truth fixtures from Phase 0 preserve the important data.

---

## Backend Track

### B1. Creation Pipeline

**File:** `backend/app/creator/llm.py` (CREATE)

Extract `_build_model()` from `backend/app/creator/agent.py` into a shared module:

```python
from app.config import settings

def build_model():
    """Build PydanticAI model from config. Used by both old agent and new pipeline."""
    if settings.local_llm_url:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        return OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
        )
    return settings.llm_model
```

**File:** `backend/app/creator/questions.py` (CREATE)

```python
from dataclasses import dataclass
from typing import Callable
import re

@dataclass
class Question:
    key: str
    prompt_template: str  # {name} substituted at call time
    max_tokens: int
    parse: Callable[[str], int | float | bool | str]

def parse_int(s: str) -> int:
    m = re.search(r'\d+', s.strip())
    return int(m.group()) if m else 0

def parse_float(s: str) -> float:
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

VISUAL_QUESTION = Question("visual_description",
    "Describe {name} for a 2D game sprite artist in 1-2 sentences. Focus on shape, material, colors, distinctive features. Describe only the object, not a scene.",
    60, parse_text)

DESTRUCTION_QUESTION = Question("destruction_result_name",
    "When {name} is destroyed, what remains? Reply with a 1-3 word name for the debris (e.g. 'broken glass shards', 'pile of splinters', 'metal scraps'). If nothing remains, reply 'nothing'.",
    8, parse_text)
```

**File:** `backend/app/creator/pipeline.py` (CREATE)

```python
import asyncio, uuid, time, structlog
from pydantic_ai import Agent
from app.cache.manager import CacheManager
from app.creator.llm import build_model
from app.creator.questions import CREATION_QUESTIONS, VISUAL_QUESTION, DESTRUCTION_QUESTION, Question
from app.models.blueprint import GameObjectBlueprint, VisualDescriptor

logger = structlog.get_logger()

async def _ask(question: Question, name: str) -> tuple[str, any]:
    """Ask one LLM question, return (key, parsed_value)."""
    prompt = question.prompt_template.format(name=name)
    agent = Agent(
        build_model(),
        output_type=str,
        model_settings={"max_tokens": question.max_tokens, "temperature": 0.3},
    )
    result = await agent.run(prompt)
    return (question.key, question.parse(result.output))

async def create_object(description: str, cache: CacheManager) -> GameObjectBlueprint:
    """V3 creation: cache check → parallel fan-out → assemble blueprint."""
    name = description.strip()
    cache_key = CacheManager.normalize_key(name)

    # Check creation cache
    cached = await cache.get("creation", cache_key)
    if cached:
        logger.info("creation_cache_hit", name=name)
        return GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **cached)

    t0 = time.monotonic()

    # Fan-out: all questions in parallel
    all_questions = CREATION_QUESTIONS + [VISUAL_QUESTION, DESTRUCTION_QUESTION]
    results = await asyncio.gather(
        *[_ask(q, name) for q in all_questions],
        return_exceptions=True,
    )

    # Assemble, handle failures with defaults
    props = {}
    for i, r in enumerate(results):
        q = all_questions[i]
        if isinstance(r, Exception):
            logger.warning("question_failed", key=q.key, error=str(r))
            if q.key == "visual_description":
                props[q.key] = f"a {name}"
            elif q.key == "destruction_result_name":
                props[q.key] = "nothing"
            elif q.parse == parse_bool:
                props[q.key] = False
            else:
                props[q.key] = 0
        else:
            props[q.key] = r[1]

    # Clamp
    props["mass_kg"] = max(0.001, min(100000, props.get("mass_kg", 1.0)))
    props["height_cm"] = max(1, min(5000, props.get("height_cm", 50)))
    for k in ("friction", "bounce", "gravity", "armor", "hp"):
        props[k] = max(0, min(100, props.get(k, 50)))
    props["field_range_cm"] = max(0, min(5000, props.get("field_range_cm", 0)))
    props["affordance"] = max(0, min(3, props.get("affordance", 3)))
    if not props.get("has_field"):
        props["field_range_cm"] = 0

    # Derive size_category from height
    h = props["height_cm"]
    size_cat = "tiny" if h <= 5 else "small" if h <= 40 else "medium" if h <= 150 else "large" if h <= 400 else "huge"

    # Handle destruction result
    destruction_name = props.get("destruction_result_name", "nothing")
    if destruction_name.lower() in ("nothing", "none", ""):
        destruction_name = ""

    blueprint_data = {
        "name": name,
        "mass_kg": props["mass_kg"], "height_cm": props["height_cm"],
        "friction": props["friction"], "bounce": props["bounce"], "gravity": props["gravity"],
        "armor": props["armor"], "hp": props["hp"],
        "indestructible": bool(props.get("indestructible", False)),
        "has_field": bool(props.get("has_field", False)),
        "field_range_cm": props["field_range_cm"],
        "autonomous": bool(props.get("autonomous", False)),
        "affordance": props["affordance"],
        "visual_descriptor": {"visual_description": props.get("visual_description", f"a {name}"), "size_category": size_cat},
        "destruction_result_name": destruction_name,
    }

    await cache.set("creation", cache_key, blueprint_data)

    # If destruction result is non-empty, pre-cache its creation too (background)
    if destruction_name:
        asyncio.create_task(_precache_destruction_result(destruction_name, cache))

    elapsed = time.monotonic() - t0
    logger.info("object_created", name=name, elapsed=round(elapsed, 2))
    return GameObjectBlueprint(id=str(uuid.uuid4()), description=description, **blueprint_data)

async def _precache_destruction_result(name: str, cache: CacheManager) -> None:
    """Pre-cache the destruction result blueprint so destruction feels instant."""
    cache_key = CacheManager.normalize_key(name)
    if await cache.exists("creation", cache_key):
        return
    try:
        await create_object(name, cache)
        logger.info("destruction_result_precached", name=name)
    except Exception as e:
        logger.warning("destruction_result_precache_failed", name=name, error=str(e))
```

### B1 test file

**File:** `backend/tests/test_creation_pipeline.py` (CREATE)

```python
"""Phase B1: creation pipeline unit tests (mock LLM)."""
from unittest.mock import AsyncMock, patch
from app.creator.questions import parse_int, parse_float, parse_bool, parse_text

def test_parse_int():
    assert parse_int("42") == 42
    assert parse_int("the answer is 42 kg") == 42
    assert parse_int("") == 0

def test_parse_float():
    assert parse_float("1.5") == 1.5
    assert parse_float("about 0.001 kg") == 0.001

def test_parse_bool():
    assert parse_bool("1") is True
    assert parse_bool("0") is False
    assert parse_bool("0 no") is False

def test_parse_text():
    assert parse_text("  a flaming sword  ") == "a flaming sword"

# Integration test with mocked LLM (tests full pipeline assembly + caching)
# async def test_create_object_caches(tmp_path):
#     ... mock _ask, verify cache.set called, second call hits cache
```

### B1 validation

```bash
cd backend && uv run pytest tests/test_creation_pipeline.py -v
```

---

### B2. LLM Quality Gate

**Before proceeding to B3 or any client work**, validate that 1-token LLM answers produce reasonable physics. This is the biggest risk in the entire project.

**File:** `backend/tests/test_llm_quality_gate.py` (CREATE)

```python
"""LLM quality gate: run creation pipeline against known objects, validate physics.

This test costs real LLM calls. Not in `make test`. Run manually:
    cd backend && uv run pytest tests/test_llm_quality_gate.py -v -s
"""
import json, pytest
from pathlib import Path
from app.creator.pipeline import create_object
from app.cache.manager import CacheManager

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
    await db.execute("""CREATE TABLE cache (
        cache_type TEXT NOT NULL, cache_key TEXT NOT NULL,
        value_json TEXT NOT NULL, model_version TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (cache_type, cache_key))""")
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
```

### B2 validation

```bash
cd backend && uv run pytest tests/test_llm_quality_gate.py -v -s
# All 19 expectations should pass. If >3 fail, the decomposition approach needs
# prompt tuning before proceeding. DO NOT continue to B3 until this gate passes.
```

Also test creation cache deduplication:

```bash
make cli-create PROMPT="fire sword"
make cli-create PROMPT="fire sword"
# Second call should log "creation_cache_hit" and return identical physics
```

---

### B3. Pairwise Evaluator + Resolver

**File:** `backend/app/engine/pairwise.py` (CREATE)

```python
import asyncio, structlog
from app.cache.manager import CacheManager
from app.creator.llm import build_model
from app.models.pairwise import PairwiseResult
from pydantic_ai import Agent

logger = structlog.get_logger()

def _obj_summary(bp: dict) -> str:
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
    ("damage_a",       "[{a}] collides with [{b}]. Damage to {a_name}? 0-100. Reply with just the number."),
    ("damage_b",       "[{a}] collides with [{b}]. Damage to {b_name}? 0-100. Reply with just the number."),
    ("state_change_a", "[{a}] collides with [{b}]. State change on {a_name}? 0=none, 1=add on_fire, 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded, 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet, 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten. Reply with just the number."),
    ("state_change_b", "[{a}] collides with [{b}]. State change on {b_name}? 0=none, 1=add on_fire, 2=add frozen, 3=add wet, 4=add electrified, 5=add poisoned, 6=add corroded, 7=add molten, 8=remove on_fire, 9=remove frozen, 10=remove wet, 11=remove electrified, 12=remove poisoned, 13=remove corroded, 14=remove molten. Reply with just the number."),
    ("force_b",        "[{a}] collides with [{b}]. How much force pushes {b_name}? 0-100 (0=none, 30=nudge, 70=strong, 100=explosion). Reply with just the number."),
    ("direction_b",    "[{a}] collides with [{b}]. Does {a_name} push or pull {b_name}? 0=push 1=pull. Reply with just 0 or 1."),
    ("destroy_a",      "[{a}] collides with [{b}]. Is {a_name} destroyed? 0=no 1=yes. Reply with just 0 or 1."),
    ("destroy_b",      "[{a}] collides with [{b}]. Is {b_name} destroyed? 0=no 1=yes. Reply with just 0 or 1."),
    ("mode",           "[{a}] collides with [{b}]. Instant or continuous effect? 0=instant 1=continuous (ongoing while touching). Reply with just 0 or 1."),
]

async def screen_pairs(new_bp: dict, scene_bps: list[dict], cache: CacheManager) -> list[int]:
    """Identify interesting pairs via single screening call."""
    if not scene_bps:
        return []
    scene_list = "\n".join(f"{i+1}. {_obj_summary(bp)}" for i, bp in enumerate(scene_bps))
    prompt = SCREENING_PROMPT.format(
        new_summary=_obj_summary(new_bp), new_name=new_bp["name"], scene_list=scene_list,
    )
    agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 30, "temperature": 0.3})
    result = await agent.run(prompt)
    # Parse comma-separated indices
    text = result.output.strip()
    if "none" in text.lower():
        return []
    import re
    indices = [int(m) - 1 for m in re.findall(r'\d+', text)]  # 1-indexed → 0-indexed
    return [i for i in indices if 0 <= i < len(scene_bps)]

async def evaluate_pair(bp_a: dict, bp_b: dict, cache: CacheManager) -> PairwiseResult:
    """Evaluate one pair: 9 parallel 1-token calls. Cache result."""
    pair_key = CacheManager.pair_key(bp_a["name"], bp_b["name"])
    cached = await cache.get("pairwise", pair_key)
    if cached:
        return PairwiseResult(**cached)

    # Lexicographic A/B order
    names = sorted([bp_a["name"].lower(), bp_b["name"].lower()])
    a_bp = bp_a if bp_a["name"].lower() == names[0] else bp_b
    b_bp = bp_b if bp_b["name"].lower() == names[1] else bp_a
    a_sum, b_sum = _obj_summary(a_bp), _obj_summary(b_bp)

    async def _ask_pairwise(key: str, template: str) -> tuple[str, int]:
        prompt = template.format(a=a_sum, b=b_sum, a_name=a_bp["name"], b_name=b_bp["name"])
        agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 2, "temperature": 0.3})
        r = await agent.run(prompt)
        import re
        m = re.search(r'\d+', r.output.strip())
        return (key, int(m.group()) if m else 0)

    results = await asyncio.gather(
        *[_ask_pairwise(k, t) for k, t in PAIRWISE_QUESTIONS],
        return_exceptions=True,
    )
    props = {}
    for i, r in enumerate(results):
        k = PAIRWISE_QUESTIONS[i][0]
        props[k] = r[1] if not isinstance(r, Exception) else 0

    result = PairwiseResult(
        damage_a=min(100, max(0, props.get("damage_a", 0))),
        damage_b=min(100, max(0, props.get("damage_b", 0))),
        state_change_a=min(14, max(0, props.get("state_change_a", 0))),
        state_change_b=min(14, max(0, props.get("state_change_b", 0))),
        force_b=min(100, max(0, props.get("force_b", 0))),
        direction_b=1 if props.get("direction_b", 0) else 0,
        destroy_a=bool(props.get("destroy_a", 0)),
        destroy_b=bool(props.get("destroy_b", 0)),
        mode=1 if props.get("mode", 0) else 0,
    )
    await cache.set("pairwise", pair_key, result.model_dump())
    return result

async def evaluate_new_object(new_bp: dict, scene_bps: list[dict], cache: CacheManager) -> None:
    """Screen + full-eval all interesting pairs for a newly spawned object."""
    interesting = await screen_pairs(new_bp, scene_bps, cache)
    logger.info("pairwise_screening", new=new_bp["name"], interesting=len(interesting), total=len(scene_bps))
    await asyncio.gather(*[evaluate_pair(new_bp, scene_bps[i], cache) for i in interesting])
```

**File:** `backend/app/engine/resolver.py` (REWRITE)

```python
from app.cache.manager import CacheManager
from app.models.pairwise import PairwiseResult

class V3Resolver:
    def __init__(self, cache: CacheManager):
        self._cache = cache

    async def resolve(self, name_a: str, name_b: str) -> PairwiseResult | None:
        pair_key = CacheManager.pair_key(name_a, name_b)
        data = await self._cache.get("pairwise", pair_key)
        return PairwiseResult(**data) if data else None
```

### B3 API wiring

**File:** `backend/app/routers/objects.py` (MODIFY)

- Import `from app.creator.pipeline import create_object` (replaces `from app.creator.agent import create_object`)
- Construct `CacheManager(request.app.state.cache_db)` and pass to `create_object()`
- After blueprint creation, schedule pairwise eval:
  ```python
  session = await manager.get_session(session_id)
  scene_bps = [obj.blueprint.model_dump() for obj in session.objects if obj.object_id != blueprint.id]
  task2 = asyncio.create_task(evaluate_new_object(blueprint.model_dump(), scene_bps, cache))
  _background_tasks.add(task2)
  task2.add_done_callback(_background_tasks.discard)
  ```

**File:** `backend/app/routers/rules.py` (DELETE)

**File:** `backend/app/routers/sessions.py` (MODIFY)

Remove `_RULES_JSON`, `_RULES_ETAG`, and all rules from session create/restore responses.

**File:** `backend/app/routers/pairwise.py` (CREATE)

```python
router = APIRouter(prefix="/api/pairwise", tags=["pairwise"])

@router.get("/scene/{session_id}")
async def get_scene_pairwise(session_id: str, request: Request) -> dict:
    """Bulk-fetch all cached pairwise results for objects in this session."""
    db = request.app.state.db
    cache_db = request.app.state.cache_db
    manager = SessionManager(db)
    cache = CacheManager(cache_db)
    session = await manager.get_session(session_id)
    if not session:
        raise HTTPException(404)
    names = [obj.blueprint.name for obj in session.objects]
    results = await cache.get_all_for_names("pairwise", names)
    return {"pairs": results}
```

Register in `main.py`: `from app.routers import pairwise` / `app.include_router(pairwise.router)`.

### B3 WebSocket pairwise delivery

**File:** `backend/app/ws/handler.py` (MODIFY)

Add `send_pairwise_ready(session_id, pair_key, result_dict)`. Called by pairwise evaluator background task after each pair completes. Also add handler for client→server `reevaluate_creature` messages.

### B3 test file

**File:** `backend/tests/test_pairwise.py` (CREATE)

```python
"""Phase B3: pairwise evaluator unit tests (mock LLM)."""
from app.models.pairwise import PairwiseResult
from app.cache.manager import CacheManager

def test_pairwise_result_defaults():
    pr = PairwiseResult()
    assert pr.damage_a == 0
    assert pr.destroy_a is False
    assert pr.mode == 0

def test_pair_key_deterministic():
    assert CacheManager.pair_key("B", "A") == CacheManager.pair_key("A", "B")

# async def test_evaluate_pair_caches(tmp_path):
#     ... mock LLM, verify cache written, second call returns cached
```

### B3 validation

```bash
cd backend && uv run pytest tests/test_pairwise.py -v
make cli-create PROMPT="fire sword"
make cli-create PROMPT="wooden shield"
# Check logs for pairwise_screening + cache writes
```

---

### B4. Creature Behavior + Destruction Cache

**File:** `backend/app/engine/creature_behavior.py` (CREATE)

```python
import asyncio, structlog
from dataclasses import dataclass
from pydantic_ai import Agent
from app.creator.llm import build_model

logger = structlog.get_logger()

@dataclass
class CreatureBehavior:
    target_name: str
    movement: int      # 0=approach, 1=flee, 2=orbit, 3=ignore
    strength: int      # 0-100
    action: int        # 0=nothing, 1=damage, 2=heal, 3=add state, 4=remove state, 5=destroy, 6=take
    action_param: int  # damage/heal amount or state_id

SCENE_PREFIX = "Scene: [{scene_list}].\n"

MOVEMENT_PROMPT = SCENE_PREFIX + "{creature} sees [{target}]. 0=approach 1=flee 2=orbit 3=ignore. Reply with just the number."
STRENGTH_PROMPT = SCENE_PREFIX + "How strongly does {creature} react to [{target}]? 0=ignores, 25=mild interest, 50=moderate, 75=strong drive, 100=absolute priority. Reply with just the number."
ACTION_PROMPT = SCENE_PREFIX + "{creature} is {movement_desc} [{target}] and {motivation}. On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take. Reply with just the number."
PARAM_DAMAGE_PROMPT = "{creature} will damage [{target}]. How much damage? 0-100. Reply with just the number."
PARAM_HEAL_PROMPT = "{creature} will heal [{target}]. How much healing? 0-100. Reply with just the number."
PARAM_STATE_PROMPT = "{creature} will {action} a state on [{target}]. Which? 1=on_fire 2=frozen 3=wet 4=electrified 5=poisoned 6=corroded 7=molten. Reply with just the number."

MOVEMENT_DESCS = {0: "APPROACHING", 1: "FLEEING", 2: "ORBITING"}
MOTIVATIONS = {0: "wants to interact with it", 2: "is cautious about it"}

async def evaluate_creature_behaviors(
    creature_bp: dict,
    scene_bps: list[dict],
    scene_inventory: list[str],
) -> list[CreatureBehavior]:
    """3-stage sequential evaluation for one creature against all scene objects."""
    creature_name = creature_bp["name"]
    scene_str = ", ".join(scene_inventory)

    # Stage 1+1b: movement + strength (all pairs, parallel)
    async def _ask_movement(target_name: str) -> tuple[str, int]:
        prompt = MOVEMENT_PROMPT.format(scene_list=scene_str, creature=creature_name, target=target_name)
        agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 1, "temperature": 0.3})
        r = await agent.run(prompt)
        import re; m = re.search(r'\d', r.output); return (target_name, int(m.group()) if m else 3)

    async def _ask_strength(target_name: str) -> tuple[str, int]:
        prompt = STRENGTH_PROMPT.format(scene_list=scene_str, creature=creature_name, target=target_name)
        agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 1, "temperature": 0.3})
        r = await agent.run(prompt)
        import re; m = re.search(r'\d+', r.output); return (target_name, int(m.group()) if m else 0)

    movement_results = await asyncio.gather(
        *[_ask_movement(bp["name"]) for bp in scene_bps], return_exceptions=True)
    strength_results = await asyncio.gather(
        *[_ask_strength(bp["name"]) for bp in scene_bps], return_exceptions=True)

    # Assemble stage 1 results
    behaviors = []
    stage2_pairs = []
    for i, bp in enumerate(scene_bps):
        mv = movement_results[i][1] if not isinstance(movement_results[i], Exception) else 3
        st = strength_results[i][1] if not isinstance(strength_results[i], Exception) else 0
        cb = CreatureBehavior(target_name=bp["name"], movement=mv, strength=st, action=0, action_param=0)
        behaviors.append(cb)
        if mv in (0, 2):  # approach or orbit → needs action evaluation
            stage2_pairs.append((i, cb))

    # Stage 2: action (approaching/orbiting pairs only, parallel)
    async def _ask_action(idx: int, cb: CreatureBehavior) -> tuple[int, int]:
        desc = MOVEMENT_DESCS.get(cb.movement, "APPROACHING")
        mot = MOTIVATIONS.get(cb.movement, "wants to interact with it")
        prompt = ACTION_PROMPT.format(
            scene_list=scene_str, creature=creature_name, target=cb.target_name,
            movement_desc=desc, motivation=mot)
        agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 1, "temperature": 0.3})
        r = await agent.run(prompt)
        import re; m = re.search(r'\d', r.output); return (idx, int(m.group()) if m else 0)

    if stage2_pairs:
        action_results = await asyncio.gather(
            *[_ask_action(idx, cb) for idx, cb in stage2_pairs], return_exceptions=True)
        for r in action_results:
            if not isinstance(r, Exception):
                idx, action = r
                behaviors[idx].action = action

    # Stage 3: parameters (actions needing them, parallel)
    stage3_pairs = [(i, b) for i, b in enumerate(behaviors) if b.action in (1, 2, 3, 4)]

    async def _ask_param(idx: int, cb: CreatureBehavior) -> tuple[int, int]:
        if cb.action in (1,):
            prompt = PARAM_DAMAGE_PROMPT.format(creature=creature_name, target=cb.target_name)
        elif cb.action in (2,):
            prompt = PARAM_HEAL_PROMPT.format(creature=creature_name, target=cb.target_name)
        else:
            act = "add" if cb.action == 3 else "remove"
            prompt = PARAM_STATE_PROMPT.format(creature=creature_name, target=cb.target_name, action=act)
        agent = Agent(build_model(), output_type=str, model_settings={"max_tokens": 2, "temperature": 0.3})
        r = await agent.run(prompt)
        import re; m = re.search(r'\d+', r.output); return (idx, int(m.group()) if m else 0)

    if stage3_pairs:
        param_results = await asyncio.gather(
            *[_ask_param(idx, cb) for idx, cb in stage3_pairs], return_exceptions=True)
        for r in param_results:
            if not isinstance(r, Exception):
                idx, param = r
                behaviors[idx].action_param = param

    # Filter out ignore (movement=3) from returned behaviors
    return [b for b in behaviors if b.movement != 3]
```

### B4 test file

**File:** `backend/tests/test_creature_behavior.py` (CREATE)

```python
"""Phase B4: creature behavior evaluation tests."""
from app.engine.creature_behavior import CreatureBehavior

def test_creature_behavior_dataclass():
    cb = CreatureBehavior(target_name="donut", movement=0, strength=90, action=5, action_param=0)
    assert cb.movement == 0
    assert cb.action == 5

# async integration tests with mock LLM for staged evaluation
```

### B4 validation

```bash
cd backend && uv run pytest tests/test_creature_behavior.py -v
```

---

## Client Track

Can proceed in parallel with Backend Track after Phase 1. Use hardcoded test blueprints until integration.

### C1. State System + Physics

#### C1a. State contradictions

**File:** `godot/scripts/data/state_contradictions.gd` (CREATE)

```gdscript
class_name StateContradictions

const CONTRADICTIONS: Dictionary = {
    "on_fire": ["frozen", "wet"],
    "frozen": ["on_fire", "molten"],
    "wet": ["on_fire"],
    "molten": ["frozen"],
}

static func get_contradictions(state: String) -> Array:
    return CONTRADICTIONS.get(state, [])
```

#### C1b. State manager

**File:** `godot/scripts/systems/state_manager.gd` (CREATE)

Same structure as existing `tag_manager.gd` but with 7-state vocabulary. Signals: `state_added(state)`, `state_removed(state)`, `states_changed(states)`. On `add_state()`, auto-remove contradictions via `StateContradictions.get_contradictions()`.

#### C1c. State decay

**File:** `godot/scripts/systems/state_decay.gd` (MODIFY)

Change `remove_tag()` parent calls to `remove_state()`. Functionally identical timer-based removal.

#### C1d. State colors

**File:** `godot/scripts/data/state_colors.gd` (CREATE)

```gdscript
class_name StateColors

const COLORS: Dictionary = {
    "on_fire": Color(1.0, 0.5, 0.0),
    "frozen": Color(0.5, 0.8, 1.0),
    "wet": Color(0.3, 0.5, 0.8),
    "electrified": Color(1.0, 1.0, 0.3),
    "poisoned": Color(0.3, 0.8, 0.3),
    "corroded": Color(0.6, 0.4, 0.2),
    "molten": Color(1.0, 0.3, 0.0),
}
const HEAL: Color = Color(0.3, 1.0, 0.3)

static func get_color(state: String) -> Color:
    return COLORS.get(state, Color.WHITE)

static func is_stateful(body: Node) -> bool:
    return body.has_method("get_states")
```

#### C1e. Physics applicator — direct blueprint reads

**File:** `godot/scenes/game_object/physics_applicator.gd` (REWRITE)

```gdscript
func apply_from_blueprint(bp: Dictionary) -> void:
    var mass_kg: float = bp.get("mass_kg", 1.0)
    var friction_pct: int = bp.get("friction", 50)
    var bounce_pct: int = bp.get("bounce", 0)
    var gravity_pct: int = bp.get("gravity", 50)
    var height_cm: int = bp.get("height_cm", 50)

    # Damping: light large things (feather) = high, heavy small (bullet) = low
    var damping: float = clampf(float(height_cm) / (mass_kg * 100.0 + 10.0), 0.0, 10.0)

    # Gravity: 0→-0.5 (floats), 50→1.0 (normal), 100→2.0 (heavy)
    var gravity_scale: float = lerpf(-0.5, 2.0, gravity_pct / 100.0)

    var size_cat: String = bp.get("visual_descriptor", {}).get("size_category", "medium")
    var mass_mult: float = PhysicsComposer.get_size_mass_multiplier(size_cat)

    apply_physics({
        "mass": mass_kg * mass_mult,
        "gravity": gravity_scale,
        "friction": friction_pct / 100.0,
        "bounce": bounce_pct / 100.0,
        "damping": damping,
    }, size_cat)
```

No SubstancePhysics dependency. No runtime tag modifiers.

#### C1f. Field system

**File:** `godot/scripts/systems/field_system.gd` (CREATE)

Reads `has_field` and `field_range_cm` directly from blueprint. Creates Area2D with blueprint-specified radius. Periodic tick (2s) routes through CollisionResolver.

```gdscript
func init_field(owner: Node, bp: Dictionary) -> void:
    _owner = owner
    if not bp.get("has_field", false):
        return
    var range_cm: int = bp.get("field_range_cm", 100)
    var range_px: float = range_cm * 0.5  # conversion factor
    _create_area(range_px)
    _start_periodic_timer()
```

#### C1 validation

```
# Create test scene with hardcoded V3 blueprint dicts
# Verify: object has correct mass/gravity/bounce
# Verify: add_state("on_fire") auto-removes "frozen"
# Verify: state decay timer fires
```

---

### C2. Collision + Effects

#### C2a. Game object — V3 init

**File:** `godot/scenes/game_object/game_object.gd` (MODIFY)

In `init_from_blueprint()`:
- Remove: `_tag_manager` creation, tag init, tag signal wiring
- Remove: `_categories` parsing, `compiled_behaviors` handling
- Add: Create `StateManager` child, wire `state_added`/`states_changed` signals
- Add: `_autonomous = bp.get("autonomous", false)`, add to "living" group if true
- Add: Create field system if `bp.get("has_field", false)`
- Replace: `get_tags()` → `get_states()` (keep `get_tags()` as alias returning states during transition)
- Replace: `add_tag()`/`remove_tag()` → `add_state()`/`remove_state()`
- Remove: `_reapply_physics()` — V3 physics are fixed at creation

#### C2b. Collision resolver — pairwise lookup

**File:** `godot/scripts/systems/collision_resolver.gd` (MODIFY)

Replace `RuleEngine.find_matching_rules(tags_a, tags_b)` with:

```gdscript
func resolve_and_notify(body_a: Node, body_b: Node, cascade_depth: int = 0,
        trigger_mode_filter: String = "", resolved: Dictionary = {}) -> void:
    var name_a: String = body_a.blueprint.get("name", "")
    var name_b: String = body_b.blueprint.get("name", "")
    if name_a.is_empty() or name_b.is_empty():
        return

    var pair_result: Dictionary = Backend.get_pairwise(name_a, name_b)
    if pair_result.is_empty():
        return  # uncached = nothing happens

    # Map to lexicographic A/B
    var sorted_names: Array = [name_a.to_lower(), name_b.to_lower()]
    sorted_names.sort()
    var a_body: Node = body_a if name_a.to_lower() == sorted_names[0] else body_b
    var b_body: Node = body_b if name_b.to_lower() == sorted_names[1] else body_a

    # Dedup check
    var dedup_key: String = "%s:%s:%s" % [a_body.get_instance_id(), b_body.get_instance_id(), trigger_mode_filter]
    if dedup_key in resolved:
        return
    resolved[dedup_key] = true

    var states_changed: bool = EffectExecutor.execute_pairwise(pair_result, a_body, b_body)

    # Cascade if states changed
    if states_changed and cascade_depth < MAX_CASCADE_DEPTH:
        _cascade_to_neighbors(a_body, cascade_depth + 1, resolved)
        _cascade_to_neighbors(b_body, cascade_depth + 1, resolved)
```

#### C2c. Effect executor — V3 outcomes

**File:** `godot/scripts/systems/effect_executor.gd` (MODIFY)

Add:

```gdscript
const STATES := ["on_fire", "frozen", "wet", "electrified", "poisoned", "corroded", "molten"]
const DYNAMIC_STATE_DURATION := 10.0

static func execute_pairwise(result: Dictionary, body_a: Node, body_b: Node) -> bool:
    var states_changed := false

    if result.get("damage_a", 0) > 0:
        WorldMutations.apply_damage(body_a, result["damage_a"])
    if result.get("damage_b", 0) > 0:
        WorldMutations.apply_damage(body_b, result["damage_b"])

    states_changed = _apply_state_change(result.get("state_change_a", 0), body_a) or states_changed
    states_changed = _apply_state_change(result.get("state_change_b", 0), body_b) or states_changed

    if result.get("force_b", 0) > 0:
        var dir: Vector2 = (body_b.global_position - body_a.global_position).normalized()
        if result.get("direction_b", 0) == 1:
            dir = -dir
        WorldMutations.apply_impulse(body_b, dir, result["force_b"] * 5.0)
        var mass_ratio: float = body_b.mass / maxf(body_a.mass, 0.01)
        WorldMutations.apply_impulse(body_a, -dir, result["force_b"] * 5.0 * mass_ratio)

    if result.get("destroy_a", false):
        body_a.take_damage(99999)
    if result.get("destroy_b", false):
        body_b.take_damage(99999)

    return states_changed

static func _apply_state_change(code: int, body: Node) -> bool:
    if code == 0:
        return false
    if code >= 1 and code <= 7:
        body.add_state(STATES[code - 1], DYNAMIC_STATE_DURATION)
        return true
    elif code >= 8 and code <= 14:
        body.remove_state(STATES[code - 8])
        return true
    return false
```

#### C2d. World mutations

**File:** `godot/scripts/systems/world_mutations.gd` (MODIFY)

- `apply_add_tag()` → `apply_add_state()`: use `StateContradictions` instead of `TagContradictions`
- `apply_remove_tag()` → `apply_remove_state()`

#### C2 validation

```
# With hardcoded pairwise results in Backend._pairwise_cache:
# {"fire sword::wooden shield": {damage_b: 40, state_change_b: 1, ...}}
# Collide fire sword + wooden shield → shield takes 40 damage + gains on_fire
# Collide water + on_fire shield → on_fire removed
# State contradictions: add frozen to on_fire object → on_fire removed
```

---

### C3. State Visuals + Physics Animations

#### C3a. State visuals

**File:** `godot/scripts/data/state_visuals.gd` (CREATE)

```gdscript
class_name StateVisuals

const STATE_PARTICLES: Dictionary = {
    "on_fire": {"color": Color(1, 0.5, 0), "direction": Vector2.UP, "amount": 12},
    "wet": {"color": Color(0.3, 0.5, 0.8), "direction": Vector2.DOWN, "amount": 6},
    "electrified": {"color": Color(1, 1, 0.3), "direction": Vector2.ZERO, "amount": 8},
    "poisoned": {"color": Color(0.3, 0.8, 0.3), "direction": Vector2.UP, "amount": 6},
    "corroded": {"color": Color(0.6, 0.4, 0.2), "direction": Vector2.DOWN, "amount": 4},
    "molten": {"color": Color(1, 0.3, 0), "direction": Vector2.UP, "amount": 10},
}
const STATE_SHADERS: Dictionary = {
    "frozen": "res://shaders/ice.gdshader",
    "molten": "res://shaders/ripple.gdshader",
}
const STATE_COLOR_SHIFTS: Dictionary = {
    "frozen": Color(0.5, 0.8, 1.0),
    "poisoned": Color(0.3, 0.8, 0.3),
    "corroded": Color(0.6, 0.4, 0.2),
}
const STATE_LIGHTS: Dictionary = {
    "on_fire": {"color": Color(1, 0.6, 0.2), "energy": 0.8, "texture_scale": 64.0},
    "molten": {"color": Color(1, 0.4, 0.1), "energy": 0.5, "texture_scale": 48.0},
}
```

#### C3b. Object visual — physics-derived + state-keyed

**File:** `godot/scenes/game_object/object_visual.gd` (MODIFY)

Replace tag-keyed animation tables:

```gdscript
func init_from_blueprint(bp: Dictionary) -> void:
    # Physics-derived animations
    if bp.get("gravity", 50) < 25:
        _add_animation("bobbing", {"amplitude": 3.0, "speed": 2.0})
    if bp.get("autonomous", false):
        _add_animation("breathing", {"amplitude": 0.03, "speed": 1.5})
    # bounce > 60 → squash/stretch on collision (checked in collision callback)

func refresh_state_visuals(states: Array) -> void:
    _clear_state_effects()
    for state in states:
        if state in StateVisuals.STATE_PARTICLES:
            _add_particles(state, StateVisuals.STATE_PARTICLES[state])
        if state in StateVisuals.STATE_SHADERS:
            _apply_shader(StateVisuals.STATE_SHADERS[state])
        if state in StateVisuals.STATE_COLOR_SHIFTS:
            _apply_color_shift(StateVisuals.STATE_COLOR_SHIFTS[state])
        if state in StateVisuals.STATE_LIGHTS:
            _add_light(StateVisuals.STATE_LIGHTS[state])
```

Dropped visuals: swaying (WIND_SOURCE), alpha pulse (GLOWING), jitter (EXPLOSIVE/BRITTLE) — no V3 equivalent.

#### C3 validation

```
# Object with gravity=10 (balloon): bobs up and down
# Autonomous creature: breathes (scale pulse)
# Object gains on_fire state: orange particles + PointLight2D
# Object gains frozen state: blue tint shader
```

---

## Phase INT — Integration

Wire backend and client together. Both tracks must be complete.

### INT-a. Backend autoload updates

**File:** `godot/autoloads/backend.gd` (MODIFY)

- Remove: `fetch_rules()`, `RuleEngine.load_rules()` calls
- Add: `var _pairwise_cache: Dictionary = {}`
- Add: `func get_pairwise(name_a: String, name_b: String) -> Dictionary`:
  ```gdscript
  func get_pairwise(name_a: String, name_b: String) -> Dictionary:
      var a := name_a.to_lower().strip_edges()
      var b := name_b.to_lower().strip_edges()
      if a > b:
          var tmp := a; a = b; b = tmp
      var key := a + "::" + b
      return _pairwise_cache.get(key, {})
  ```
- Add: `func fetch_scene_pairwise(session_id: String)` — calls `GET /api/pairwise/scene/{session_id}`, populates `_pairwise_cache`
- Add: Handle WebSocket messages:
  - `pairwise_ready` → update `_pairwise_cache[pair_key] = result`
  - `creature_behaviors` → forward to creature's VerbBehaviorSystem

### INT-b. Creature re-evaluation triggers

**File:** `godot/scenes/game_object/game_object.gd` (MODIFY)

In `_on_states_changed()`:
```gdscript
func _on_states_changed(_updated_states: Array) -> void:
    object_visual.refresh_state_visuals(_states)
    if _tag_field != null:
        _tag_field.on_states_changed(_states)
    EventBus.object_tags_changed.emit(self)  # keep signal name for backward compat
    # Request creature behavior re-evaluation for nearby autonomous objects
    Backend.request_reevaluation(object_id, "state_change")
```

**File:** `godot/autoloads/backend.gd` (MODIFY)

```gdscript
func request_reevaluation(object_id: String, reason: String) -> void:
    if _ws_connected:
        _ws.send_text(JSON.stringify({
            "type": "reevaluate_creature",
            "creature_id": object_id,
            "reason": reason,
        }))
```

Backend receives this, re-runs creature behavior evaluation, sends updated `creature_behaviors` message back.

### INT-c. Remove rule_engine autoload

Update `godot/project.godot` to remove `RuleEngine` from autoloads. Delete `godot/autoloads/rule_engine.gd`.

### INT-d. Validation

```bash
make dev
# Full integration test:
# 1. Create "fire sword" — backend returns V3 blueprint, Godot renders with correct physics
# 2. Create "wooden shield" — pairwise eval runs, WebSocket delivers pairwise_ready
# 3. Collide fire sword + wooden shield — pairwise cache lookup → damage + on_fire
# 4. Create "bucket of water" — pairwise eval against both existing objects
# 5. Collide water + on_fire shield — on_fire removed
# 6. State decay after 10s if not re-applied
```

---

## Phase 5 — Creature Behavior (Godot)

### 5A. Verb behavior system rewrite

**File:** `godot/scripts/systems/verb_behavior_system.gd` (REWRITE)

```gdscript
# Receives behaviors from backend via WebSocket:
# [{target_name: "donut", movement: 0, strength: 90, action: 5, action_param: 0}, ...]

var _behaviors: Array = []
var _perception_range: float = 400.0
const MELEE_RANGE := 48.0
const MELEE_COOLDOWN := 1.0

func init_behaviors(behaviors: Array, owner: Node) -> void:
    _owner = owner
    _behaviors = behaviors

func update_behaviors(behaviors: Array) -> void:
    """Called when backend sends updated creature_behaviors."""
    _behaviors = behaviors

func _physics_process(delta: float) -> void:
    if _behaviors.is_empty():
        return

    # Utility-based priority selection
    var best_target: Node = null
    var best_utility: float = -1.0
    var best_behavior: Dictionary = {}

    for behavior in _behaviors:
        var target := _find_target_by_name(behavior["target_name"])
        if target == null or not is_instance_valid(target):
            continue
        var dist: float = _owner.global_position.distance_to(target.global_position)
        var utility: float = float(behavior["strength"]) / (1.0 + dist / _perception_range)
        if behavior["movement"] == 1:  # flee
            utility *= 1.5
        if utility > best_utility:
            best_utility = utility
            best_target = target
            best_behavior = behavior

    if best_target == null:
        return

    match best_behavior["movement"]:
        0: _approach(best_target)
        1: _flee_from(best_target)
        2: _orbit(best_target)

    # On-arrival action for approach/orbit
    if best_behavior["movement"] in [0, 2]:
        var dist: float = _owner.global_position.distance_to(best_target.global_position)
        if dist < MELEE_RANGE:
            _execute_action(best_behavior, best_target)

func _execute_action(behavior: Dictionary, target: Node) -> void:
    match behavior["action"]:
        0: pass  # nothing
        1: WorldMutations.apply_damage(target, behavior["action_param"])
        2: WorldMutations.apply_heal(target, behavior["action_param"])
        3: target.add_state(EffectExecutor.STATES[behavior["action_param"] - 1])
        4: target.remove_state(EffectExecutor.STATES[behavior["action_param"] - 1])
        5: target.take_damage(99999)
        6: pass  # take — requires affordance system
```

### 5B. Wire creature behavior delivery

**File:** `godot/autoloads/backend.gd` (MODIFY)

Handle `creature_behaviors` WebSocket message:
```gdscript
"creature_behaviors":
    var creature_id: String = msg["creature_id"]
    var creature := _find_game_object(creature_id)
    if creature and creature._behavior_system:
        creature._behavior_system.update_behaviors(msg["behaviors"])
```

### 5C. Test file

**File:** `backend/tests/test_creature_behavior_quality.py` (CREATE)

```python
"""Creature behavior quality gate (costs LLM calls, run manually).
    cd backend && uv run pytest tests/test_creature_behavior_quality.py -v -s
"""
import yaml, pytest
from pathlib import Path
from app.engine.creature_behavior import evaluate_creature_behaviors

FIXTURES = yaml.safe_load((Path(__file__).parent.parent / "evals/fixtures/v2_creature_behaviors.yaml").read_text())

@pytest.mark.parametrize("fixture", FIXTURES[:10], ids=lambda f: f"{f['creature']}+{f['target']}")
async def test_creature_behavior(fixture):
    creature_bp = {"name": fixture["creature"], "mass_kg": 70, "armor": 30, "hp": 80}
    target_bp = {"name": fixture["target"], "mass_kg": 1, "armor": 10, "hp": 50}
    scene_inventory = [fixture["creature"], fixture["target"]]
    behaviors = await evaluate_creature_behaviors(creature_bp, [target_bp], scene_inventory)
    assert len(behaviors) >= 1
    b = behaviors[0]
    expected_mv = {"approach": 0, "flee": 1, "orbit": 2, "ignore": 3}[fixture["expected_movement"]]
    assert b.movement == expected_mv, f"Expected {fixture['expected_movement']}, got movement={b.movement}"
```

### 5D. Validation

```
# Create "zombie cop" + "donut" → zombie approaches donut
# Create "campfire" → zombie flees fire
# Zombie breathes (autonomous=true visual)
```

---

## Phase 6 — Affordances

Carry/mount/climb is entirely new engine code with no V2 equivalent.

### 6A. Affordance system

**File:** `godot/scripts/systems/affordance_system.gd` (CREATE)

```gdscript
class_name AffordanceSystem extends Node

var _held_object: Node = null
var _mounted_object: Node = null
const INTERACT_RANGE := 64.0
const THROW_IMPULSE := 500.0

func try_interact(player: CharacterBody2D) -> bool:
    """Called when player presses interact. Returns true if interaction started."""
    if _held_object:
        _drop_or_throw(player)
        return true
    if _mounted_object:
        _dismount(player)
        return true
    var nearest := _find_nearest_interactable(player)
    if nearest == null:
        return false
    var affordance: int = nearest.blueprint.get("affordance", 3)
    match affordance:
        0: _carry(player, nearest)
        1: _mount(player, nearest)
        2: pass  # climb handled by overlap detection
        3: return false
    return true

func _carry(player: Node, obj: Node) -> void:
    _held_object = obj
    obj.freeze = true
    obj.reparent(player.get_node("HandMarker"))
    obj.position = Vector2.ZERO

func _drop_or_throw(player: Node) -> void:
    var obj := _held_object
    _held_object = null
    obj.reparent(player.get_parent())
    obj.freeze = false
    obj.global_position = player.global_position + Vector2(32, 0) * player.facing
    # If player is moving, throw with impulse
    if player.velocity.length() > 50:
        obj.apply_impulse(player.velocity.normalized() * THROW_IMPULSE)

func _mount(player: Node, obj: Node) -> void:
    _mounted_object = obj
    player.reparent(obj)
    player.position = Vector2(0, -32)  # sit on top
    # Player input now steers the mounted object

func _dismount(player: Node) -> void:
    var obj := _mounted_object
    _mounted_object = null
    player.reparent(obj.get_parent())
    player.global_position = obj.global_position + Vector2(0, -48)
```

### 6B. Swing/attack with held object

When the player swings a held object, check overlaps during the arc and apply the held object's pairwise interactions against targets:

```gdscript
func _swing(player: Node) -> void:
    # Tween hand rotation through arc
    # During arc, check held object overlaps
    # For each overlap: look up pairwise(held.name, target.name) and execute
```

### 6C. Climb detection

Handled in player script: while overlapping an object with affordance=2, player gains upward velocity.

### 6D. Validation

```
# Create "sword" (affordance=0) → press interact → player picks it up
# Swing sword at wooden shield → held object's pairwise interaction fires
# Throw sword → reparent to scene with impulse
# Create "horse" (affordance=1) → press interact → player mounts
# Create "ladder" (affordance=2) → player climbs while overlapping
```

---

## Phase 7 — Environment Bodies + Final Cleanup

### 7A. Environment bodies as named GameObjects

**File:** `godot/scenes/environment_body/environment_body.gd` (REWRITE)

Environment bodies become indestructible objects in the pairwise cache (Option A).

Level scripts define env bodies as V3 blueprint dicts:

```gdscript
func _create_env_body(pos: Vector2, size: Vector2, env_name: String, color: Color, solid: bool) -> Node:
    var bp: Dictionary = {
        "id": env_name + "_" + str(randi()),
        "name": env_name,
        "description": env_name,
        "mass_kg": 99999, "height_cm": int(size.y),
        "friction": 50, "bounce": 0, "gravity": 50,
        "armor": 100, "hp": 0, "indestructible": true,
        "has_field": true, "field_range_cm": int(size.x * 0.6),
        "autonomous": false, "affordance": 3,
        "visual_descriptor": {"visual_description": env_name, "size_category": "large"},
        "destruction_result_name": "", "states": [],
    }
    # Instantiate StaticBody2D, init field system, register in pairwise cache
```

At level load, backend evaluates pairwise interactions between env bodies and seed objects.

### 7B. Backend V2 file deletion

| Delete | Reason |
|--------|--------|
| `backend/app/models/substances.py` | Replaced by LLM physics |
| `backend/app/models/tags.py` | Replaced by 7 states |
| `backend/app/models/tag_behaviors.py` | Replaced by creature behavior evaluator |
| `backend/app/models/rules.py` | Replaced by pairwise cache |
| `backend/app/models/effects.py` | Replaced by PairwiseResult fields |
| `backend/app/engine/rules_data.py` | Replaced by pairwise cache |
| `backend/app/engine/trait_deriver.py` | Replaced by LLM physics |
| `backend/app/creator/agent.py` | Replaced by pipeline.py |

### 7C. Godot V2 file deletion

| Delete | Reason |
|--------|--------|
| `godot/scripts/data/substance_physics.gd` | Physics read from blueprint |
| `godot/scripts/data/field_config.gd` | Field reads from blueprint |
| `godot/scripts/data/tag_animations.gd` | Replaced by state_visuals.gd |
| `godot/scripts/data/tag_colors.gd` | Replaced by state_colors.gd |
| `godot/scripts/data/tag_contradictions.gd` | Replaced by state_contradictions.gd |
| `godot/scripts/data/tag_descriptions.gd` | No V3 equivalent |
| `godot/scripts/data/behavior_display.gd` | No V3 equivalent |
| `godot/scripts/systems/tag_manager.gd` | Replaced by state_manager.gd |
| `godot/scripts/systems/tag_field.gd` | Replaced by field_system.gd |
| `godot/autoloads/rule_engine.gd` | Replaced by pairwise cache lookup |

### 7D. Docs cleanup

- Archive to `docs/archive/`: `ARCHITECTURE.md`, `GAME_DESIGN.md`, `action-plan.md`
- Keep and update: `LEVEL_DESIGN.md` (V3 format), `scribblenauts-deep-dive.md`, `llm-behavior-systems.md`
- `CLAUDE.md` — rewrite for V3 only after all code is working

### 7E. Final validation

```bash
make check  # lint + typecheck + test
make dev
# Full game loop:
# 1. Fire sword + wooden shield → damage + on_fire
# 2. Water + fire → extinguish
# 3. Zombie cop + donut → approach + eat
# 4. Pick up sword, swing at zombie → held object pairwise interaction
# 5. Acid pool (env body) damages objects via pairwise cache
# 6. State cascade: fire spreads to nearby flammable objects
# 7. Destroyed object spawns destruction result (from destruction_result cache)
```

---

## Open Design Decisions — Resolutions

**Environment bodies: Option A** — named objects in pairwise cache. The LLM naturally answers "acid pool hits wooden bridge → damage 40, add corroded." No special cases. Level pre-warming (ship seeded cache.db) eliminates first-load latency.

**Eval system: Rebuild incrementally.** Phase 0 extracts ground truth. New metrics after core loop works: physics reasonableness (calibrate against V2 substance physics), pairwise quality (calibrate against V2 rules), creature behavior quality (calibrate against hand-authored fixtures). Keep Visual Clarity + Has Signature. Delete Substance/Element/Category/Tag metrics.

**Visual triggers: Physics-derived + state-keyed.** `gravity<25` → bobbing, `autonomous` → breathing, `bounce>60` → squash/stretch. States drive runtime visuals. Dropped: swaying, alpha pulse, jitter (no V3 equivalent).

**Pairwise state invalidation: Lazy re-eval with safe fallback.** Mark stale on state change. Use base result as fallback on collision. Re-evaluate async (~145ms) with active states in prompt.

---

## Risk Mitigation

1. **LLM answer quality (HIGH)** — Phase B2 is an explicit quality gate. 19 expectations must pass before continuing. If >3 fail, tune prompts before proceeding.

2. **Pairwise cache consistency (HIGH)** — Same pair must produce same results. Creation cache ensures deterministic physics. Pairwise cache keyed by normalized sorted names. Test thoroughly in B3.

3. **Parallel track drift (MEDIUM)** — Backend and client tracks share the JSON wire format from Phase 1. Any format change requires updating both sides. The wire format section at the top of this doc is the contract.

4. **Session migration (LOW)** — Old game.db won't deserialize new blueprints. Wipe game.db for V3 dev. Cache.db starts empty.

5. **Affordance complexity (MEDIUM)** — Carry/mount/climb is new engine code with reparenting, input redirection, and collision layer management. Giving it its own phase (6) isolates this risk.
