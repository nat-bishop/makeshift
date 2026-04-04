# Object System V2

## Why

The current system has the LLM pick 2-5 from 27 boolean tags and write a behavior in a DSL it's bad at (accuracy was so low we cut from 2-4 behaviors to 0-1). Tags are boolean — a rusty dagger and an enchanted greatsword both get [SHARP, METALLIC] and deal identical damage. Behaviors can only target "nearest living thing" — a wolf can't distinguish prey from threats. The engine only has 10 verbs, so objects like rope swings, containers, and mounts can't exist.

## What Changes

The LLM's 27-tag decision is factored into three small, intuitive selections — inspired by how Dark Souls splits weapon identity into base type + infusion. Substance provides numeric physics (like Dwarf Fortress materials). Behavior targeting uses embeddings for semantic matching (like The Sims' object advertisement system, but learned instead of hand-authored).

**Before:**
```
tags: [RIGID, SHARP, HEAT_SOURCE, METALLIC, HOT]     pick 2-5 from 27
signature: "ON_CONTACT -> SPAWN_PROJECTILE, power=high"   DSL notation
```

**After:**
```
substance: "metal"        1 of 16 — determines physics
element: "burning"        0-1 of 7 — energy infusion
tags: [SHARP]             0-3 of ~10 — independent modifiers
behaviors:                0-4 verb + freeform target
  - destroy → "criminals and lawbreakers"
  - eat → "food, especially donuts"
```

The backend derives internal traits (same Tag enum the rule engine already uses) from substance + element + explicit tags. It also computes a numeric substance profile for physics, a combat profile for parameterized rule damage, and embeddings for behavior targeting. The existing rule engine, collision resolver, and field system are untouched.

---

## Stage 1 — Backend

Replace the LLM schema and object creation pipeline. The Godot client works unchanged during this stage because V2 blueprints include backward-compatible `tags` and V1-format `behaviors`.

### 1. Substance + Element Data

- [ ] Create `backend/app/models/substances.py`
  - [ ] `Substance` StrEnum: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, slime, ice, lava, fire, smoke, flesh
  - [ ] `SubstanceState` StrEnum: solid, liquid, gas, energy
  - [ ] `SubstanceProfile` Pydantic model: mass, durability, friction, conductivity, burn_rate, specific_heat, heat_output, state
  - [ ] `SUBSTANCE_PROFILES` dict with all 16 profiles (values below)
  - [ ] `SUBSTANCE_AUTO_TRAITS` dict — each substance's implied internal traits
  - [ ] `Element` StrEnum: burning, electric, magnetic, freezing, acidic, toxic, windy
  - [ ] `ELEMENT_TRAITS` dict — each element's internal traits
  - [ ] `ELEMENT_PROFILE_OVERRIDES` dict — profile modifications per element

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

- [ ] Create `backend/app/engine/trait_deriver.py`
  - [ ] `derive_traits(substance, element, tags, behaviors) -> list[Tag]`
    - Union of: substance auto-traits + element traits + explicit tags + behavior-derived (has `destroy` verb → HOSTILE)
  - [ ] `resolve_profile(substance, element, tags) -> SubstanceProfile`
    - Start with substance base, apply element overrides, apply tag modifiers, clamp to valid ranges
  - [ ] `compute_combat_profile(profile: SubstanceProfile) -> dict`
    - Pre-compute: `melee_damage` = clamp(25 * mass / 1.5, 10, 60), `crush_damage` = clamp(20 * mass / 5.0, 10, 60), `fire_dps_coefficient` = 10 * heat_output, plus passthrough `conductivity` and `mass`
- [ ] Tests in `backend/tests/test_trait_deriver.py`
  - [ ] metal + burning + [SHARP] → traits [HEAT_SOURCE, HOT, METALLIC, RIGID, SHARP], heat_output=1.0
  - [ ] ice + null + [HEAVY] → traits [BRITTLE, COLD, FROZEN, HEAVY, RIGID], mass=7.0
  - [ ] flesh + null + [LIVING] + destroy verb → traits [HOSTILE, LIVING]
  - [ ] rubber + null + [LIGHT] → traits [BOUNCY, INSULATING, LIGHT], mass=0.12
  - [ ] glass + acidic + [] → traits [ACIDIC, BREAKABLE, REFLECTIVE]
  - [ ] metal + null + [SHARP] melee_damage=50, cloth + null + [SHARP] melee_damage=10

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

- [ ] Update `backend/app/models/tags.py`
  - [ ] Add `LLM_VISIBLE_TAGS_V2` frozenset: SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET
  - [ ] Keep full Tag enum and existing `LLM_VISIBLE_TAGS` — internal rules still need all values
- [ ] Replace `CreatorOutputSpec` in `backend/app/models/blueprint.py`
  - [ ] New fields: substance (Substance), element (Element | None), tags (list[Tag], max 3, from V2 visible set), behaviors (list[BehaviorVerbSpec], max 4)
  - [ ] `BehaviorVerb` StrEnum: destroy, eat, investigate, follow, protect, flee
  - [ ] `BehaviorVerbSpec` model: verb + target (str, non-empty, max 100 chars)
  - [ ] Keep: name validation, visual_descriptor
  - [ ] Remove: signature field and its validator
- [ ] Update `GameObjectBlueprint` in `backend/app/models/blueprint.py`
  - [ ] Add: substance, element, substance_profile (dict), combat_profile (dict), identity_embedding (list[float]), behavior_embeddings (list[list[float]])
  - [ ] `tags` field now computed by `derive_traits()` — backward-compatible with Godot client
  - [ ] `behaviors` field: convert V2 verbs to V1 Behavior objects for Godot backward compat
  - [ ] `starting_durability` now from substance profile instead of tag-based (50/150/200)
- [ ] Replace `create_object()` in `backend/app/creator/agent.py`
  - [ ] New system prompt (~80 lines): substance menu (16), element menu (7), tag menu (~10), behavior verbs (6) with examples
  - [ ] Pipeline: LLM → derive_traits → resolve_profile → compute_combat_profile → compute_embeddings → assemble blueprint
- [ ] Update `backend/app/routers/objects.py` to call the new creation function
- [ ] Remove `backend/app/models/behaviors.py` (V1 DSL parser — no longer needed)
- [ ] Update `backend/app/models/tag_behaviors.py`
  - [ ] `LIVING` with no behaviors → default `investigate → "interesting nearby objects"`
  - [ ] `LIVING` with `destroy` → also add `flee → "overwhelming threats"`
  - [ ] V2→V1 behavior conversion for Godot compat: destroy→MOVE_TOWARD+HOSTILE, eat→MOVE_TOWARD, flee→MOVE_AWAY, investigate→PATROL, follow→MOVE_TOWARD, protect→MOVE_TOWARD

### 4. Embeddings

- [ ] Create `backend/app/embeddings.py`
  - [ ] `embed_texts(texts: list[str]) -> list[list[float]]` — batched call to Google `text-embedding-004` (768-dim). Uses existing `GOOGLE_API_KEY`. Lazy singleton.
  - [ ] `build_identity_text(name, substance, element, visual_description) -> str` — format: `"{name} — {substance} {element or ''} {visual_description}"`
  - [ ] `compute_object_embeddings(output: CreatorOutputSpec) -> tuple[list[float], list[list[float]]]` — one batched API call returning (identity_embedding, [target_embeddings])
  - [ ] `TRAIT_STATE_TEXTS` dict — ~10 entries: HEAT_SOURCE → "burning, on fire, aflame", FROZEN → "frozen, icy, covered in ice", ELECTRIC → "electrified, sparking", WET → "wet, soaked", TOXIC → "poisonous, toxic", GLOWING → "glowing, luminous", HOT → "hot, heated", COLD → "cold, chilled", BRITTLE → "brittle, fragile", CORRODED → "corroded, weakened by acid"
  - [ ] `get_trait_embeddings() -> dict[Tag, list[float]]` — lazy-computed, cached. Embeds all trait-state texts once.
  - [ ] If embedding call fails: return empty lists. Behaviors degrade to V1-style NEAREST_LIVING targeting in Godot.
- [ ] Tests in `backend/tests/test_embeddings.py`
  - [ ] Returns 768-dim vectors
  - [ ] Donut identity vs "food, especially donuts" → dot product > 0.5
  - [ ] Donut identity vs "criminals and lawbreakers" → dot product < 0.3
  - [ ] HEAT_SOURCE trait embedding vs "fires and burning things" → dot product > 0.5

### 5. Eval + Integration Tests

- [ ] Update eval cases (at least 20 key cases) with expected substance + element
  - [ ] "fire sword" → substance: metal, element: burning, tags: [SHARP]
  - [ ] "rock" → substance: stone, element: null, tags: []
  - [ ] "acid spider" → substance: flesh, element: acidic, tags: [LIVING]
  - [ ] "campfire" → substance: fire, element: null, tags: []
  - [ ] "ice wall" → substance: ice, element: null, tags: []
  - [ ] "rubber duck" → substance: rubber, element: null, tags: [LIGHT]
- [ ] Add substance/element accuracy metrics
- [ ] End-to-end: POST `/api/sessions/{id}/objects` returns blueprint with substance_profile, combat_profile, identity_embedding, and backward-compatible tags
- [ ] `make check` passes

### Stage 1 done when

- [ ] V2 agent produces valid blueprints for 20+ objects
- [ ] V2-derived traits match V1 expected tags for >80% of eval cases
- [ ] Embedding dot products pass spot checks
- [ ] Existing Godot client works unchanged (backward-compatible tags + V1-format behaviors in blueprint)

---

## Stage 2 — Godot + Cleanup

Make the Godot client consume V2 data: substance-based physics, verb behavior system with embedding targeting, parameterized rules. Then remove V1 code.

### 6. Substance-Based Physics

- [ ] Create `godot/scripts/data/substance_physics.gd`
  - [ ] Read `substance_profile` from blueprint → resolve {mass, gravity, friction, bounce, damping}
  - [ ] State-derived defaults: solid (gravity=1.0, damping=0.5), liquid (1.0, 2.0), gas (-0.2, 4.0), energy (0.0, 0.0)
  - [ ] Apply tag modifiers: HEAVY, LIGHT, BOUNCY, STICKY, FLYING (same values as backend)
- [ ] Update `physics_composer.gd` — use substance profile instead of TagPhysicsMap
- [ ] Update `physics_applicator.gd` — pass blueprint to composer
- [ ] Update `game_object.gd` — store substance_profile and combat_profile from blueprint, read starting_durability from blueprint
- [ ] Remove `tag_physics_map.gd`

**Test:** Metal sword heavier than cloth flag. Rubber ball bounces. Debug overlay shows substance-derived values.

### 7. Verb Behavior System

- [ ] Extract `godot/scripts/systems/movement_utils.gd` from `behavior_executor.gd`
  - [ ] `apply_movement_force()`, `apply_patrol()`, friction compensation, velocity clamping
- [ ] Create `godot/scripts/systems/verb_behavior_system.gd`
  - [ ] Read `behavior_embeddings` and verb specs from blueprint
  - [ ] Read `identity_embedding` from each nearby game object
  - [ ] Hardcode ~10 trait-state embedding vectors (same values the backend computes)
  - [ ] Target scan every 0.3s: for each behavior, score nearby objects via `max(dot(target, identity), dot(target, trait_embedding[t]) for t in dynamic_traits)`. Pick highest above 0.5.
  - [ ] Verb execution: destroy (move+melee), eat (move+consume+heal), investigate (move slowly, stop at 128px), follow (move, maintain 64px), protect (follow+attack threats), flee (move away)
  - [ ] Priority: flee=1, protect=2, destroy=3, eat=4, follow=5, investigate=6. Highest active verb gets movement.
- [ ] Update `game_object.gd` — store identity_embedding, attach VerbBehaviorSystem
- [ ] Remove `behavior_executor.gd` and `behavior_maps.gd`

**Test:** Cop eats donut, attacks robber, flees ghost. Firefighter targets tree that catches fire mid-scene.

### 8. Parameterized Rules

- [ ] Update `effect_executor.gd` — read combat_profile/substance_profile from objects for parameterized rules:
  - [ ] `sharp_living_cut`: source `combat_profile.melee_damage` instead of hardcoded 25
  - [ ] `sharp_breakable_damage`: source `combat_profile.melee_damage`
  - [ ] `heavy_breakable_crush`: source `combat_profile.crush_damage`
  - [ ] `heat_flammable_ignite`: source `combat_profile.fire_dps_coefficient` × target `substance_profile.burn_rate`
  - [ ] `electric_metallic_electrify`: 30 × target `substance_profile.conductivity`
  - [ ] `wind_light_push`: 45 × (0.3 / target `substance_profile.mass`)
  - [ ] `reflective_heat_reflect`: 10 × source `substance_profile.heat_output`

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

- [ ] Remove V1 code: old system prompt, `CreatorOutputSpec.signature`, V1 implied behaviors, V1→V2 behavior conversion shims, old `LLM_VISIBLE_TAGS`
- [ ] Remove obsolete `TAG_CONTRADICTIONS` pairs (substance/element structure prevents them)
- [ ] Remove obsolete `TAG_AUTO_CORRECTIONS` entries
- [ ] Update CLAUDE.md, ARCHITECTURE.md, GAME_DESIGN.md
- [ ] Update all eval cases with V2 expected values
- [ ] `make check` passes

### Stage 2 done when

- [ ] Metal sword feels heavier than wooden stick in-game
- [ ] Cop/donut/robber/ghost embedding targeting works
- [ ] Firefighter targets burning tree (trait-state augmentation works)
- [ ] Greatsword deals more damage than dagger (parameterized rules)
- [ ] All existing levels playable
- [ ] No V1 behavior code remains
- [ ] Docs updated

---

## Reference

### Tags absorbed by substance (removed from LLM vocab)

LIQUID, GAS, RIGID, METALLIC, INSULATING, FROZEN, MOLTEN, FLAMMABLE — all auto-derived from substance choice.

### Tags absorbed by element (removed from LLM vocab)

HEAT_SOURCE, HOT, ELECTRIC, MAGNETIC, COLD, ACIDIC, TOXIC, WIND_SOURCE — the element field replaces these. 0-1 constraint prevents contradictions.

### Tags remaining (~11, LLM picks 0-3)

SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET

HOSTILE is auto-derived from having a `destroy` verb.

### Behavior targeting

Every object gets a 768-dim identity embedding (from name + substance + visual). Every behavior target gets a 768-dim embedding (from freeform text). Runtime matching is dot products. Dynamic state (tree catches fire) is handled by pre-computed trait-state embeddings (~10 vectors) that augment the identity score:

```
score = max(
    dot(target_embedding, object.identity_embedding),
    max(dot(target_embedding, trait_embedding[t]) for t in object.dynamic_traits)
)
```

### Examples

**Fire sword** — `substance: metal, element: burning, tags: [SHARP]`
→ internal traits: [HEAT_SOURCE, HOT, METALLIC, RIGID, SHARP]
→ mass: 3.0, durability: 250, melee_damage: 50, fire_dps_coeff: 10

**Cop** — `substance: flesh, element: null, tags: [LIVING], behaviors: [eat→"food, especially donuts", destroy→"criminals", flee→"ghosts"]`
→ internal traits: [HOSTILE, LIVING] (HOSTILE from destroy verb)
→ targets donut over sword via embedding similarity

**Dagger vs greatsword** — both `substance: metal, tags: [SHARP]`, but dagger is size=small (mass 1.5) and greatsword is size=large + [SHARP, HEAVY] (mass 8.0)
→ dagger melee_damage: 25, greatsword melee_damage: 60
