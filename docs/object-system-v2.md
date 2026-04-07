# Object System V2

## Why

The current system has the LLM pick 2-5 from 27 boolean tags and write a behavior in a DSL it's bad at (accuracy was so low we cut from 2-4 behaviors to 0-1). Tags are boolean — a rusty dagger and an enchanted greatsword both get [SHARP, METALLIC] and deal identical damage. Behaviors can only target "nearest living thing" — a wolf can't distinguish prey from threats. The engine only has 10 verbs, so objects like rope swings, containers, and mounts can't exist.

## What Changes

The LLM's 27-tag decision is factored into three small, intuitive selections — inspired by how Dark Souls splits weapon identity into base type + infusion. Substance provides numeric physics (like Dwarf Fortress materials). Behavior targeting uses local embeddings for semantic matching (like The Sims' object advertisement system, but learned instead of hand-authored).

**Before:**
```
tags: [RIGID, SHARP, HEAT_SOURCE, METALLIC, HOT]     pick 2-5 from 27
signature: "ON_CONTACT -> SPAWN_PROJECTILE, power=high"   DSL notation
```

**After:**
```
substance: "metal"        1 of 16 — determines physics
element: "burning"        0-1 of 7 — energy infusion
tags: [SHARP]             0-3 of ~12 — independent modifiers
behaviors:                0-4 verb + freeform target
  - destroy → "criminals and lawbreakers"
  - eat → "food, especially donuts"
```

The backend derives internal traits (same Tag enum the rule engine already uses) from substance + element + explicit tags. It computes a numeric substance profile for physics, a combat profile for parameterized rule damage, and 1024-dim embeddings via a local model for behavior targeting. The existing rule engine, collision resolver, and field system are untouched.

## Behavior System

### Verbs

6 verbs. Target is always freeform text, always embedded locally.

| Verb | Mechanical Action | New Engine Work |
|------|------------------|-----------------|
| **destroy** | Move toward + melee damage cycle | Small: melee attack action |
| **eat** | Move toward + consume (damage target, heal self, destroy target) | Small: consume action |
| **investigate** | Move toward slowly, stop at medium range | Trivial: stop-distance |
| **follow** | Move toward, maintain close distance | Trivial: follow-distance |
| **protect** | Follow target + destroy threats near it | Medium: two-state machine |
| **flee** | Move away at high speed | None: existing MOVE_AWAY |

Deferred: use, ride, steal (each needs new engine systems).

### Priority = List Order

The LLM puts the most important behavior first. Position in the behaviors array defines what this creature cares about most. No fixed priority table — the LLM decides character through ordering.

A donut-obsessed cop:
```
1. eat → "food, especially donuts"       ← eats while the world burns
2. destroy → "criminals and lawbreakers"
3. flee → "supernatural monsters"         ← only flees if nothing else to do
```

A brave warrior (no flee behavior at all):
```
1. destroy → "enemies and monsters"       ← charges in
2. protect → "innocent people"
```

A cowardly villager:
```
1. flee → "anything dangerous or scary"   ← always runs first
2. investigate → "interesting things"
```

Multiple same-verb entries are allowed: two `destroy` behaviors with different targets. The LLM will usually consolidate into one target string, but the option exists.

### Implied Behaviors

Minimal. V1 needed extensive implied behaviors because the LLM was bad at writing them. V2 doesn't — freeform text is easy for the LLM. The system prompt guides the LLM to write behaviors for living creatures.

Only one default: `LIVING` tag with empty behaviors list → append `investigate → "interesting nearby objects"` (wander, so a creature isn't completely static if the LLM forgets).

No implied flee, no implied chase, no category-based defaults. The LLM controls all behavior. EXPLOSIVE detonation is handled by the rule engine, not the behavior system.

### Embedding-Based Targeting (Event-Driven)

Every object gets a 1024-dim identity embedding. Every behavior target gets a 1024-dim embedding. Matching is event-driven — no polling, no per-frame scanning. The LLM only runs at spawn. Everything after that is string concatenation, local embedding (~5ms), and dot products.

**Model: `qwen3-embedding:0.6b`** via Ollama.
- 0.6B params, 1024 dimensions, ~640MB on disk (Q8 quantized)
- <5ms per embedding on GPU, ~10-50ms on CPU
- STS score 86.57 — best-in-class, beats 7B+ models on semantic similarity
- Supports MRL (Matryoshka) — can truncate to 256 or 128 dims if needed
- Deployment: `ollama pull qwen3-embedding:0.6b`, then `POST /api/embed` — no Python deps needed
- Apache 2.0 license

#### Three components

**1. Object identity embedding.** Built from name + visual description + tag phrases for ALL current tags. When any tag changes, rebuild the string and re-embed locally (~1ms). Broadcast a `changed` event.

Each tag maps to a short natural-language fragment (1-3 words) that reads well in a comma-separated list. No distinction between "static" and "dynamic" tags — all tags get phrases, any tag can change at any time.

```python
TAG_PHRASES = {
    # LLM-visible tags
    SHARP: "sharp-edged",         HEAVY: "very heavy",        LIGHT: "lightweight",
    BOUNCY: "bouncy and elastic", BREAKABLE: "fragile",       STICKY: "sticky",
    REFLECTIVE: "shiny",          EXPLOSIVE: "explosive",     FLYING: "flying",
    LIVING: "alive",              WET: "wet and soaked",       HOSTILE: "hostile",
    # Substance-derived
    RIGID: "hard and rigid",      METALLIC: "metallic",       INSULATING: "insulating",
    FLAMMABLE: "flammable",       LIQUID: "liquid",           GAS: "gaseous",
    FROZEN: "frozen solid",       MOLTEN: "molten",
    # Element-derived
    HEAT_SOURCE: "on fire",       HOT: "hot",                 ELECTRIC: "electrified",
    MAGNETIC: "magnetic",         COLD: "freezing cold",      ACIDIC: "corrosive",
    TOXIC: "poisonous",           WIND_SOURCE: "generating wind",
    # Internal (added by rules)
    BRITTLE: "brittle",           CORRODED: "corroded",       GLOWING: "glowing",
}

SIZE_PHRASES = {"tiny": "tiny", "small": "small", "large": "large", "huge": "towering and huge"}
# "medium" omitted (default, not worth mentioning)

def build_embed_string(name, visual_description, size_category, current_tags):
    parts = [name, visual_description]
    if size_category in SIZE_PHRASES:
        parts.append(SIZE_PHRASES[size_category])
    parts.extend(TAG_PHRASES[t] for t in sorted(current_tags) if t in TAG_PHRASES)
    return ", ".join(parts)
```

No distinction between "static" and "dynamic" tags. All tags are treated the same. When Medusa petrifies a villager (removes LIVING, adds RIGID + BREAKABLE), the identity updates from `"Villager, a frightened peasant, alive, living creature"` to `"Villager, a frightened peasant, rigid, hard, fragile, breakable"`. Re-embed, broadcast. A wolf that was chasing the villager as prey loses the match — "alive, living creature" is gone.

**2. Behavior target embeddings.** Computed once at entity spawn, cached forever. A cop with `eat → "donuts"` gets one vector that never changes.

**3. Event-driven matching.** Runs on two triggers only — never polls:
- **Object enters scene:** Dot-product the new object's embedding against every behavior vector in the scene. Above threshold → add to that creature's target list. Below → skip.
- **Object's tags change:** Re-embed, then dot-product against every behavior vector. Update target lists (add if now above threshold, remove if now below).

Per-frame, the verb behavior system just picks the best target from the pre-computed target list by distance + behavior priority order. No dot products in the frame loop.

#### What runs when

| Event | What happens | LLM? | Embed calls |
|-------|-------------|------|-------------|
| Entity spawns | Embed each behavior target | No | 1 per behavior |
| Object spawns | LLM generates blueprint, embed identity | Yes | 1 |
| Tag added/removed | Rebuild string from name + visual + tag phrases, re-embed | No | 1 |
| Matching | Dot product vs all behavior vectors | No | 0 |
| Per-frame movement | Pick nearest from target list | No | 0 |

The LLM fires exactly once per object, at birth. Every other operation is string concat, a local embed (~1ms), or a dot product (~1μs).

#### Walkthrough: Cop, Firefighter, and a Wooden Spoon

**Setup — entity spawn:**
```
Cop spawns with behaviors: [eat → "donuts", destroy → "criminals"]
  → embed each target → cache on cop, never recomputed

Firefighter spawns with behaviors: [destroy → "burning things and fires"]
  → embed target → cache on firefighter
```

**Act 1 — spoon enters scene:**
```
Wooden Spoon spawns. tags: [RIGID, FLAMMABLE]
LLM generates visual: "a smooth wooden cooking spoon"
embed_string = "Wooden Spoon, a smooth wooden cooking spoon, rigid, hard, flammable"
→ embed → broadcast "new object"

Cop: sim("donuts", embed_string) = 0.11 → skip
Firefighter: sim("burning things and fires", embed_string) = 0.19 → skip
Result: nobody cares about the spoon.
```

**Act 2 — fire spreads, spoon ignites (tag system adds HEAT_SOURCE, HOT):**
```
embed_string = "Wooden Spoon, a smooth wooden cooking spoon, rigid, hard, flammable, burning, on fire, hot, radiating heat"
→ re-embed (~1ms) → broadcast "object changed"

Cop: sim("donuts", embed_string) = 0.09 → skip
Firefighter: sim("burning things and fires", embed_string) = 0.89 → HIT → add to target list
Result: firefighter targets the spoon.
```

**Act 3 — firefighter extinguishes it (tag system removes HEAT_SOURCE, HOT):**
```
embed_string = "Wooden Spoon, a smooth wooden cooking spoon, rigid, hard, flammable"
→ re-embed → broadcast "object changed"

Firefighter: sim("burning things and fires", embed_string) = 0.19 → miss → remove from target list
Result: firefighter loses interest.
```

**Meanwhile — donut spawns:**
```
Donut spawns. tags: [BREAKABLE]
embed_string = "Donut, a glazed sugary donut with rainbow sprinkles, fragile, breakable"
→ embed → broadcast "new object"

Cop: sim("donuts", embed_string) = 0.91 → HIT → add to target list
Firefighter: sim("burning things and fires", embed_string) = 0.07 → skip
Result: cop targets the donut.
```

---

## Implementation — Backend

Replace the LLM schema and object creation pipeline. Remove V1 behavior code (behaviors.py, DSL parser) as you go.

### 1. Substance + Element Data

- [x] Create `backend/app/models/substances.py`
  - [x] `Substance` StrEnum: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, slime, ice, lava, fire, smoke, flesh
  - [x] `SubstanceState` StrEnum: solid, liquid, gas, energy
  - [x] `SubstanceProfile` Pydantic model: mass, durability, friction, conductivity, burn_rate, specific_heat, heat_output, state
  - [x] `SUBSTANCE_PROFILES` dict with all 16 profiles (values below)
  - [x] `SUBSTANCE_AUTO_TRAITS` dict — each substance's implied internal traits
  - [x] `Element` StrEnum: burning, electric, magnetic, freezing, acidic, toxic, windy
  - [x] `ELEMENT_TRAITS` dict — each element's internal traits
  - [x] `ELEMENT_PROFILE_OVERRIDES` dict — profile modifications per element

**Substances:**

| Substance | mass | dur | fric | cond | burn | sp_heat | heat | State | Auto traits |
|-----------|------|-----|------|------|------|---------|------|-------|-------------|
| metal | 3.0 | 250 | 0.6 | 0.9 | 0.0 | 0.3 | 0.0 | solid | METALLIC, RIGID |
| wood | 1.0 | 120 | 0.5 | 0.05 | 0.8 | 0.5 | 0.0 | solid | FLAMMABLE |
| stone | 4.0 | 300 | 0.7 | 0.1 | 0.0 | 0.8 | 0.0 | solid | RIGID, HEAVY |
| glass | 1.5 | 40 | 0.3 | 0.05 | 0.0 | 0.4 | 0.0 | solid | BREAKABLE, REFLECTIVE |
| rubber | 0.8 | 100 | 0.8 | 0.01 | 0.3 | 0.6 | 0.0 | solid | BOUNCY, INSULATING |
| bone | 1.8 | 150 | 0.5 | 0.05 | 0.1 | 0.5 | 0.0 | solid | RIGID |
| ceramic | 2.0 | 60 | 0.6 | 0.02 | 0.0 | 0.7 | 0.0 | solid | BREAKABLE, INSULATING |
| cloth | 0.3 | 40 | 0.4 | 0.03 | 0.9 | 0.3 | 0.0 | solid | FLAMMABLE, LIGHT |
| water | 0.8 | 9999 | 0.0 | 0.7 | 0.0 | 1.0 | 0.0 | liquid | LIQUID, WET |
| oil | 0.6 | 9999 | 0.05 | 0.01 | 1.0 | 0.4 | 0.0 | liquid | LIQUID, FLAMMABLE |
| slime | 1.2 | 9999 | 2.0 | 0.1 | 0.0 | 0.6 | 0.0 | liquid | LIQUID, STICKY, TOXIC |
| ice | 2.0 | 80 | 0.05 | 0.15 | 0.0 | 0.2 | 0.0 | solid | FROZEN, RIGID, COLD, BRITTLE |
| lava | 5.0 | 9999 | 0.9 | 0.3 | 0.0 | 0.9 | 3.0 | liquid | MOLTEN, LIQUID, HEAT_SOURCE |
| fire | 0.01 | 30 | 0.0 | 0.2 | 0.0 | 0.1 | 1.5 | energy | GAS, HEAT_SOURCE, HOT |
| smoke | 0.01 | 9999 | 0.0 | 0.0 | 0.0 | 0.1 | 0.0 | gas | GAS, LIGHT |
| flesh | 1.5 | 150 | 0.5 | 0.3 | 0.2 | 0.7 | 0.0 | solid | *(none)* |

**Elements:**

| Element | Internal traits | Profile override |
|---------|----------------|-----------------|
| burning | HEAT_SOURCE, HOT | heat_output = max(base, 1.0) |
| electric | ELECTRIC | conductivity = max(base, 0.5) |
| magnetic | MAGNETIC | — |
| freezing | COLD | — |
| acidic | ACIDIC | — |
| toxic | TOXIC | — |
| windy | WIND_SOURCE | — |

### 2. Trait Derivation

- [x] Create `backend/app/engine/trait_deriver.py`
  - [x] `derive_traits(substance, element, tags, behaviors) -> list[Tag]`
    - Union of: substance auto-traits + element traits + explicit tags + behavior-derived (has `destroy` verb → HOSTILE)
  - [x] `resolve_profile(substance, element, tags) -> SubstanceProfile`
    - Start with substance base, apply element overrides, apply tag modifiers, clamp to valid ranges
  - [x] `compute_combat_profile(profile: SubstanceProfile) -> dict`
    - Pre-compute: `melee_damage` = clamp(25 * mass / 1.5, 10, 60), `crush_damage` = clamp(20 * mass / 5.0, 10, 60), `fire_dps_coefficient` = 10 * heat_output, plus passthrough `conductivity` and `mass`
- [x] Tests in `backend/tests/test_trait_deriver.py`
  - [x] metal + burning + [SHARP] → traits [HEAT_SOURCE, HOT, METALLIC, RIGID, SHARP], heat_output=1.0
  - [x] ice + null + [HEAVY] → traits [BRITTLE, COLD, FROZEN, HEAVY, RIGID], mass=7.0
  - [x] flesh + null + [LIVING] + destroy verb → traits [HOSTILE, LIVING]
  - [x] rubber + null + [LIGHT] → traits [BOUNCY, INSULATING, LIGHT], mass=0.12
  - [x] glass + acidic + [] → traits [ACIDIC, BREAKABLE, REFLECTIVE]
  - [x] metal + null + [SHARP] melee_damage=50, cloth + null + [SHARP] melee_damage=10

**Tag profile modifiers (applied in resolve_profile):**

| Tag | Modifier |
|-----|----------|
| HEAVY | mass += 5.0, friction = max(base, 0.7) |
| LIGHT | mass *= 0.15, damping = 1.5 |
| BREAKABLE | durability *= 0.4 |
| BOUNCY | bounce = 0.9, friction = min(base, 0.2) |
| STICKY | friction = max(base, 2.0), bounce = 0.0 |
| FLYING | gravity = 0.0, damping = 2.0 |

### 3. Schema + Agent

- [x] Update `backend/app/models/tags.py`
  - [x] Add `LLM_VISIBLE_TAGS_V2` frozenset: SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET, HOSTILE
  - [x] Keep full Tag enum and existing `LLM_VISIBLE_TAGS` — internal rules still need all values
- [x] Replace `CreatorOutputSpec` in `backend/app/models/blueprint.py`
  - [x] New fields: substance (Substance), element (Element | None), tags (list[Tag], max 3, from V2 visible set), behaviors (list[BehaviorVerbSpec], max 4)
  - [x] `BehaviorVerb` StrEnum: destroy, eat, investigate, follow, protect, flee
  - [x] `BehaviorVerbSpec` model: verb + target (str, non-empty, max 100 chars)
  - [x] Keep: name validation, visual_descriptor
  - [x] Remove: signature field and its validator
- [x] Update `GameObjectBlueprint` in `backend/app/models/blueprint.py`
  - [x] Add: substance, element, substance_profile (dict), combat_profile (dict), identity_embedding (list[float]), behavior_embeddings (list[list[float]])
  - [x] `tags` field computed by `derive_traits()` — used by rule engine
  - [x] `behaviors` field stores V2 BehaviorVerbSpecs directly (verb + target + embedding)
  - [x] `starting_durability` now from substance profile instead of tag-based (50/150/200)
- [x] Replace `create_object()` in `backend/app/creator/agent.py`
  - [x] New system prompt (~80 lines): substance menu (16), element menu (7), tag menu (~12), behavior verbs (6) with examples
  - [x] System prompt: "List behaviors in order of importance. First behavior takes precedence when multiple are active."
  - [x] Pipeline: LLM → derive_traits → resolve_profile → compute_combat_profile → compute_embeddings → assemble blueprint
- [x] Update `backend/app/routers/objects.py` to call the new creation function
- [x] Remove `backend/app/models/behaviors.py` (V1 DSL parser — no longer needed)
- [x] Update `backend/app/models/tag_behaviors.py`
  - [x] Only one implied behavior: `LIVING` with empty behaviors list → append `investigate → "interesting nearby objects"` (default wander). No other implied behaviors — the LLM controls all behavior.

### 4. Local Embedding Model

- [x] Ensure Ollama is available and pull `qwen3-embedding:0.6b` (~640MB)
- [x] Create `backend/app/embeddings.py`
  - [x] `embed_texts(texts: list[str]) -> list[list[float]]` — call Ollama `POST /api/embed` with model `qwen3-embedding:0.6b`. Returns 1024-dim vectors. Batch all texts in one request.
  - [x] `TAG_PHRASES: dict[str, str]` — every tag mapped to a short natural-language phrase (see design section above). Used by both backend (initial embed) and Godot (re-embed on tag change via `/api/embed` endpoint).
  - [x] `SIZE_PHRASES: dict[str, str]` — size category → phrase ("tiny", "small", "large", "towering and huge"). Medium omitted.
  - [x] `build_embed_string(name, visual_description, size_category, current_tags) -> str` — format: `"{name}, {visual_description}, {size_phrase}, {tag phrases}"`. Includes ALL current tags.
  - [x] `compute_object_embeddings(output) -> tuple[list[float], list[list[float]]]` — build embed string + all behavior target texts, embed in one batch. Returns (identity_embedding, [target_embeddings]).
  - [x] If Ollama unavailable: return zero vectors. Behaviors degrade to random/nearest targeting in Godot.
- [x] Add `POST /api/embed` endpoint to `backend/app/routers/objects.py`
  - [x] Accepts: name, visual_description, size_category, current_tags
  - [x] Returns: 1024-dim identity embedding
  - [x] Called by Godot client when any tag is added/removed at runtime (~5ms server-side)
- [x] Tests in `backend/tests/test_embeddings.py`
  - [x] Returns 1024-dim normalized vectors
  - [x] Donut identity vs "food, especially donuts" → cosine similarity > 0.5
  - [x] Donut identity vs "criminals and lawbreakers" → cosine similarity < 0.3
  - [x] "Wooden Spoon, a smooth cooking spoon, on fire, hot" vs "fires and burning things" → high
  - [x] "Wooden Spoon, a smooth cooking spoon, hard and rigid" vs "fires and burning things" → low
  - [x] Medusa test: "Villager, a peasant, alive" vs "prey animals" → high. After petrify: "Villager, a peasant, hard and rigid, fragile" vs "prey animals" → low

### 5. Eval + Integration Tests

- [x] Update eval cases (all 90 cases) with expected substance + element
  - [x] "fire sword" → substance: metal, element: burning, tags: [SHARP]
  - [x] "rock" → substance: stone, element: null, tags: []
  - [x] "acid spider" → substance: flesh, element: acidic, tags: [LIVING]
  - [x] "campfire" → substance: fire, element: null, tags: []
  - [x] "ice wall" → substance: ice, element: null, tags: []
  - [x] "rubber duck" → substance: rubber, element: null, tags: [LIGHT]
- [x] Add substance/element accuracy metrics
- [x] End-to-end: POST `/api/sessions/{id}/objects` returns blueprint with substance_profile, combat_profile, identity_embedding, behavior_embeddings
- [x] `make check` passes

### Backend done when

- [ ] V2 agent produces valid blueprints for 20+ objects
- [ ] Embedding similarities pass spot checks
- [x] `make check` passes

---

## Implementation — Godot

Consume V2 blueprint data: substance-based physics, verb behavior system with embedding targeting, parameterized rules. Remove V1 Godot code (behavior_executor.gd, behavior_maps.gd, tag_physics_map.gd) as you go.

### 6. Substance-Based Physics

- [x] Create `godot/scripts/data/substance_physics.gd`
  - [x] Read `substance_profile` from blueprint → resolve {mass, gravity, friction, bounce, damping}
  - [x] State-derived defaults: solid (gravity=1.0, damping=0.5), liquid (1.0, 2.0), gas (-0.2, 4.0), energy (0.0, 0.0)
  - [x] Apply tag modifiers: HEAVY, LIGHT, BOUNCY, STICKY, FLYING (same values as backend)
- [x] Update `physics_composer.gd` — use substance profile instead of TagPhysicsMap
- [x] Update `physics_applicator.gd` — pass blueprint to composer
- [x] Update `game_object.gd` — store substance_profile and combat_profile from blueprint, read starting_durability from blueprint
- [x] Remove `tag_physics_map.gd`

**Test:** Metal sword heavier than cloth flag. Rubber ball bounces. Debug overlay shows substance-derived values.

### 7. Verb Behavior System (Event-Driven)

Two layers: event-driven target matching (perception) + per-frame movement (action).

- [x] Extract `godot/scripts/systems/movement_utils.gd` from `behavior_executor.gd`
  - [x] `apply_movement_force()`, `apply_patrol()`, friction compensation, velocity clamping
- [x] Expose re-embedding endpoint on backend: `POST /api/embed` accepts name + visual_description + size_category + current_tags, returns 1024-dim vector (~5ms via Ollama)
- [x] Create `godot/scripts/systems/verb_behavior_system.gd`
  - [x] **Perception layer (event-driven, no polling):**
    - Store behavior target embeddings from blueprint (immutable, cached at spawn)
    - Maintain per-behavior target lists: `target_lists[behavior_index] = [objects above threshold]`
    - Listen for `object_entered_scene` signal → dot-product new object's embedding against all behavior targets → add to target lists if above threshold (0.5)
    - Listen for `object_embedding_changed` signal → re-check against all behavior targets → update target lists
    - Listen for `object_exited_scene` signal → remove from all target lists
  - [x] **Action layer (per-frame):**
    - For each behavior in list order (priority): if target list non-empty, pick nearest by distance, execute verb, break
    - Verb execution: destroy (move+melee), eat (move+consume+heal), investigate (move slowly, stop at 128px), follow (move, maintain 64px), protect (follow+attack threats), flee (move away)
  - [x] Error handling: 5 consecutive errors disables behavior
- [x] Update `game_object.gd`
  - [x] Store `identity_embedding` as var. Expose `get_identity_embedding()`.
  - [x] `TAG_PHRASES` and `SIZE_PHRASES` dicts (mirror of backend constants)
  - [x] `_rebuild_and_reembed()`: rebuild embed string via `build_embed_string(name, visual_description, size_category, current_tags)`, call backend `POST /api/embed`, update cached vector, emit `object_embedding_changed` signal
  - [x] Call `_rebuild_and_reembed()` on any `add_tag()` or `remove_tag()` call
  - [x] Attach VerbBehaviorSystem when blueprint has behavior_embeddings
- [x] Remove `behavior_executor.gd` and `behavior_maps.gd`

**Test:** Cop eats donut, attacks robber, flees ghost (list-order priority). Firefighter targets tree that catches fire mid-scene (tag change → re-embed → firefighter's target list updates). Brave warrior with no flee behavior charges into danger. Medusa petrifies villager (LIVING removed, RIGID added → wolf loses villager from target list).

### 8. Parameterized Rules

- [x] Update `effect_executor.gd` — read combat_profile/substance_profile from objects for parameterized rules:
  - [x] `sharp_living_cut`: source `combat_profile.melee_damage` instead of hardcoded 25
  - [x] `sharp_breakable_damage`: source `combat_profile.melee_damage`
  - [x] `heavy_breakable_crush`: source `combat_profile.crush_damage`
  - [x] `heat_flammable_ignite`: source `combat_profile.fire_dps_coefficient` × target `substance_profile.burn_rate`
  - [x] `electric_metallic_electrify`: 30 × target `substance_profile.conductivity`
  - [x] `wind_light_push`: 45 × (0.3 / target `substance_profile.mass`)
  - [x] `reflective_heat_reflect`: 10 × source `substance_profile.heat_output`

**Test:** Lava deals more fire damage than campfire. Greatsword cuts harder than dagger.

### 9. New Engine Components (incremental, each independent)

Pattern for each: add Tag value → add trait_deriver mapping → build Godot component → add to system prompt.

- [ ] **holdable + throwable** — player picks up, carries, throws objects (~1 week)
- [ ] **climbable** — player climbs surfaces vertically (~1 week)
- [ ] **edible** — consume on interact, heal player, destroy object (~3 days)
- [ ] **containing** — holds child objects, releases on damage/interact (~1 week)
- [ ] **heal_field** — passive area heal for nearby LIVING (port from existing)
- [ ] **timed_explosion** — detonate on timer/damage (port from existing)
- [ ] **guard_area** — attack anything entering radius (port from existing)
- [ ] **attach_on_contact** — PinJoint2D between objects on collision (new)

### 10. Cleanup + Docs

- [x] Remove V1 code: old system prompt, `CreatorOutputSpec.signature`, old implied behaviors, old `LLM_VISIBLE_TAGS`
- [x] Remove obsolete `TAG_AUTO_CORRECTIONS` entries
- [ ] Update CLAUDE.md, ARCHITECTURE.md, GAME_DESIGN.md
- [ ] Update all eval cases with V2 expected values
- [x] `make check` passes

### Godot done when

- [ ] Metal sword feels heavier than wooden stick in-game
- [ ] Cop/donut/robber/ghost embedding targeting works with list-order priority
- [ ] Firefighter targets tree that catches fire mid-scene (event-driven re-embed + target list update)
- [ ] Medusa petrification test: wolf loses petrified villager from target list (LIVING removed → re-embed → match drops)
- [ ] Greatsword deals more damage than dagger (parameterized rules)
- [ ] All existing levels playable
- [x] Old behavior code removed (behaviors.py, behavior_executor.gd, behavior_maps.gd, tag_physics_map.gd)
- [ ] Docs updated

---

## Reference

### Tags absorbed by substance (removed from LLM vocab)

LIQUID, GAS, RIGID, METALLIC, INSULATING, FROZEN, MOLTEN, FLAMMABLE — all auto-derived from substance choice.

### Tags absorbed by element (removed from LLM vocab)

HEAT_SOURCE, HOT, ELECTRIC, MAGNETIC, COLD, ACIDIC, TOXIC, WIND_SOURCE — the element field replaces these. 0-1 constraint prevents contradictions.

### Tags remaining (~12, LLM picks 0-3)

SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET, HOSTILE

HOSTILE is also auto-derived from having a `destroy` verb, but stays LLM-visible for non-seeking hostile objects (spike traps, radioactive barrels, force fields).

### Embedding model

`qwen3-embedding:0.6b` via Ollama.
- 0.6B params, 1024 dimensions, ~640MB on disk (Q8)
- <5ms per embedding on GPU, ~10-50ms on CPU
- STS score 86.57 — best-in-class semantic similarity, beats 7B+ models
- Supports MRL — truncate to 256/128 dims if needed
- Deployment: `ollama pull qwen3-embedding:0.6b` + `POST /api/embed`
- Apache 2.0 license

### Embedding architecture

**Event-driven, not polling.** No per-frame scanning. Matching runs only when objects enter the scene or their tags change.

- Object identity = `"{name}, {visual_description}, {size_phrase}, {tag phrases for ALL current tags}"`. Re-embedded locally on any tag change (~5ms via Ollama).
- Behavior targets = embedded once at creature spawn, cached forever.
- Tag phrases cover every tag equally — no static/dynamic distinction. Any tag can change at any time (Medusa petrifies a villager → LIVING removed, RIGID added → identity re-embedded → wolves lose it from target list).
- Matching: dot product of changed object against all behavior vectors. Above threshold → added to target list. Below → removed.
- Per-frame: verb behavior system picks nearest from target list by distance. No dot products in the frame loop.

### Examples

**Fire sword** — `substance: metal, element: burning, tags: [SHARP]`
→ internal traits: [HEAT_SOURCE, HOT, METALLIC, RIGID, SHARP]
→ mass: 3.0, durability: 250, melee_damage: 50, fire_dps_coeff: 10
→ identity: `"Fire Sword, a gleaming blade wreathed in flame, sharp-edged, metallic, hard and rigid, on fire, hot"`

**Cop** — `substance: flesh, element: null, tags: [LIVING], behaviors: [eat→"food, especially donuts", destroy→"criminals", flee→"ghosts"]`
→ internal traits: [HOSTILE, LIVING] (HOSTILE from destroy verb)
→ behaviors in priority order: eat first (donut-obsessed), then destroy, then flee
→ identity: `"Officer Johnson, a stern police officer in blue uniform, alive, hostile"`

**Dagger vs greatsword** — both `substance: metal, tags: [SHARP]`, but dagger is size=small (mass 1.5) and greatsword is size=large + [SHARP, HEAVY] (mass 8.0)
→ dagger: `"Rusty Dagger, a short pitted blade, small, sharp-edged, metallic, hard and rigid"` → melee_damage: 25
→ greatsword: `"Enchanted Greatsword, a massive glowing blade, large, sharp-edged, very heavy, metallic, hard and rigid"` → melee_damage: 60

**Firefighter + burning tree** — firefighter has `destroy → "fires and burning things"`.
Tree identity starts as: `"Oak Tree, a tall tree with green leaves, large, flammable"` → low match.
Fire rule adds HEAT_SOURCE + HOT → re-embed: `"Oak Tree, a tall tree with green leaves, large, flammable, on fire, hot"` → high match → firefighter adds tree to target list.
Firefighter extinguishes it → tags removed → re-embed → back to low match → tree removed from target list.

**Medusa petrifies villager** — villager identity: `"Villager, a frightened peasant in brown clothes, alive"` → wolf has `eat → "prey animals"` → high match.
Medusa removes LIVING, adds RIGID + BREAKABLE → re-embed: `"Villager, a frightened peasant in brown clothes, hard and rigid, fragile"` → wolf's match drops → villager removed from wolf's target list.
