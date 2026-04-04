# Object System V2 — Stage 1: Backend

Stage 1 builds the entire backend for V2: substance profiles, trait derivation, new LLM schema, embedding infrastructure, combat profiles. The game continues working unchanged — V2 blueprints compute backward-compatible `tags: list[Tag]` and V1-format behaviors for the existing Godot client.

Stage 2 (separate effort): Godot physics from substance profiles, VerbBehaviorSystem, new engine components, remove old V1 code.

Full design rationale: `docs/design-object-system-v2.md` and `.claude/plans/golden-dreaming-codd.md`

---

## Design Summary

**LLM output changes from:**
```
tags: [RIGID, SHARP, HEAT_SOURCE, METALLIC, HOT]  (pick 2-5 from 27)
signature: "ON_CONTACT -> SPAWN_PROJECTILE -> NEAREST_LIVING, power=high"  (DSL)
```

**To:**
```
substance: "metal"           (1 of 16 — base physics)
element: "burning"           (0-1 of 7 — energy infusion)
tags: [SHARP]                (0-3 of ~10 — independent modifiers)
behaviors: [                 (0-4 verb + freeform target)
  {verb: "destroy", target: "criminals and lawbreakers"},
  {verb: "eat", target: "food, especially donuts"}
]
```

The backend derives internal traits (same Tag enum values the rule engine uses) from substance + element + tags. It also computes a numeric substance profile, combat profile, and identity/target embeddings. The blueprint JSON sent to Godot includes all of this plus backward-compatible `tags: list[Tag]`.

---

## Checklist

### 1. Substance Profiles

- [ ] Create `backend/app/models/substances.py`
  - [ ] `Substance` StrEnum with 16 values: metal, wood, stone, glass, rubber, bone, ceramic, cloth, water, oil, slime, ice, lava, fire, smoke, flesh
  - [ ] `SubstanceState` StrEnum: solid, liquid, gas, energy
  - [ ] `SubstanceProfile` Pydantic model with fields: mass, durability, friction, conductivity, burn_rate, specific_heat, heat_output, state
  - [ ] `SUBSTANCE_PROFILES: dict[Substance, SubstanceProfile]` — all 16 profiles with values from the table below
  - [ ] `SUBSTANCE_AUTO_TRAITS: dict[Substance, list[Tag]]` — maps each substance to its implied internal traits

**Substance profile values:**

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

### 2. Element Definitions

- [ ] Create `backend/app/models/elements.py`
  - [ ] `Element` StrEnum with 7 values: burning, electric, magnetic, freezing, acidic, toxic, windy
  - [ ] `ELEMENT_TRAITS: dict[Element, list[Tag]]` — maps each element to internal traits
  - [ ] `ELEMENT_PROFILE_OVERRIDES: dict[Element, dict]` — profile modifications per element

**Element mappings:**

| Element | Internal traits | Profile override |
|---------|----------------|-----------------|
| burning | HEAT_SOURCE, HOT | heat_output = max(base, 1.0) |
| electric | ELECTRIC | conductivity = max(base, 0.5) |
| magnetic | MAGNETIC | — |
| freezing | COLD | — |
| acidic | ACIDIC | — |
| toxic | TOXIC | — |
| windy | WIND_SOURCE | — |

### 3. Trait Derivation Engine

- [ ] Create `backend/app/engine/trait_deriver.py`
  - [ ] `derive_traits(substance, element, tags, behaviors) -> list[Tag]` — union of substance auto-traits + element traits + explicit tags + behavior-derived traits (has destroy verb → HOSTILE)
  - [ ] `resolve_substance_profile(substance, element, tags) -> dict` — start with substance profile, apply element overrides, apply tag modifiers (HEAVY → mass += 5.0, LIGHT → mass *= 0.15, BREAKABLE → durability *= 0.4, BOUNCY → bounce = 0.9, STICKY → friction = 2.0, FLYING → gravity = 0.0), clamp values
  - [ ] `compute_combat_profile(substance_profile) -> dict` — pre-compute: fire_dps_coefficient (10 * heat_output), melee_damage (clamp(25 * mass / 1.5, 10, 60)), crush_damage (clamp(20 * mass / 5.0, 10, 60)), conductivity, mass
  - [ ] `compute_durability(substance_profile, tags) -> int` — base from substance durability, BREAKABLE applies 0.4x

**Tag profile modifiers:**

| Tag | Modifier |
|-----|----------|
| HEAVY | mass += 5.0, friction = max(friction, 0.7) |
| LIGHT | mass *= 0.15, damping = 1.5 |
| BREAKABLE | durability *= 0.4 |
| BOUNCY | bounce = 0.9, friction = min(friction, 0.2) |
| STICKY | friction = max(friction, 2.0), bounce = 0.0 |
| FLYING | gravity = 0.0, damping = 2.0 |

- [ ] Unit tests in `backend/tests/test_trait_deriver.py`
  - [ ] Fire sword: metal + burning + [SHARP] → [HEAT_SOURCE, HOT, METALLIC, RIGID, SHARP]
  - [ ] Ice boulder: ice + null + [HEAVY] → [BRITTLE, COLD, FROZEN, HEAVY, RIGID], mass=7.0
  - [ ] Cop: flesh + null + [LIVING] + has destroy → [HOSTILE, LIVING]
  - [ ] Rubber duck: rubber + null + [LIGHT] → [BOUNCY, INSULATING, LIGHT], mass=0.12
  - [ ] Campfire: fire + null + [] → [GAS, HEAT_SOURCE, HOT], dur=30
  - [ ] Glass bottle: glass + acidic + [] → [ACIDIC, BREAKABLE, REFLECTIVE]
  - [ ] Profile modifier stacking: verify HEAVY on cloth, LIGHT on metal, BREAKABLE on stone
  - [ ] Combat profile: metal sharp sword melee_damage = 50, cloth dagger melee_damage = 10

### 4. Update Tag System

- [ ] Update `backend/app/models/tags.py`
  - [ ] Add `LLM_VISIBLE_TAGS_V2: frozenset[Tag]` — only the ~10 tags remaining: SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, LIVING, WET (verify final list against substance/element coverage)
  - [ ] Keep full `Tag` enum unchanged — internal traits still need all values for rule matching
  - [ ] Keep `LLM_VISIBLE_TAGS` unchanged for V1 backward compat
  - [ ] Add `TAG_PROFILE_MODIFIERS: dict[Tag, list[Modifier]]` — the tag→profile modifications from step 3, co-located with tag definitions

### 5. Behavior Verb Schema

- [ ] Create `backend/app/models/behaviors_v2.py` (new file, V1 `behaviors.py` untouched)
  - [ ] `BehaviorVerb` StrEnum: destroy, eat, investigate, follow, protect, flee
  - [ ] `BehaviorVerbSpec` Pydantic model: verb (BehaviorVerb) + target (str)
  - [ ] `VERB_PRIORITY: dict[BehaviorVerb, int]` — flee=1, protect=2, destroy=3, eat=4, follow=5, investigate=6
  - [ ] Validator: target must be non-empty, max 100 chars
  - [ ] `VERB_DESCRIPTIONS: dict[BehaviorVerb, str]` — one-line descriptions for the system prompt

### 6. Blueprint V2 Models

- [ ] Update `backend/app/models/blueprint.py`
  - [ ] `CreatorOutputV2(BaseModel)` alongside existing `CreatorOutputSpec`
    - [ ] name: str (same validation as V1 — 1-3 words)
    - [ ] substance: Substance
    - [ ] element: Element | None
    - [ ] tags: list[Tag] with min_length=0, max_length=3
    - [ ] behaviors: list[BehaviorVerbSpec] with max_length=4
    - [ ] visual_descriptor: VisualDescriptor (unchanged)
    - [ ] Validator: tags must be from `LLM_VISIBLE_TAGS_V2`
    - [ ] Validator: substance + element contradiction check (ice + burning? let trait_deriver handle, or reject?)
  - [ ] `GameObjectBlueprintV2(BaseModel)` alongside existing `GameObjectBlueprint`
    - [ ] All fields from V1: id, name, description, tags (now derived), behaviors (V1 format for Godot compat), visual_descriptor
    - [ ] New fields: substance, element, substance_profile (dict), combat_profile (dict), identity_embedding (list[float]), behavior_embeddings (list[list[float]]), starting_durability (from substance)
    - [ ] `tags` computed from `derive_traits()` — backward compatible with V1 Godot client
    - [ ] `behaviors` computed from V2 BehaviorVerbSpecs → V1 Behavior format for Godot compat (verb→action mapping: destroy→MOVE_TOWARD+damage, eat→MOVE_TOWARD+consume, flee→MOVE_AWAY, etc.)
  - [ ] Conversion function: `v2_to_blueprint(creator_output: CreatorOutputV2, description: str) -> GameObjectBlueprintV2`

### 7. Embedding Infrastructure

- [ ] Create `backend/app/embeddings/client.py`
  - [ ] `embed_texts(texts: list[str]) -> list[list[float]]` — batched call to Google `text-embedding-004`, 768-dim vectors
  - [ ] Uses `GOOGLE_API_KEY` from existing config (same key as Gemini LLM/image)
  - [ ] Lazy singleton pattern (same as `get_generate_image()`)
  - [ ] Error handling: if embedding fails, return empty lists (behaviors degrade to V1 NEAREST_LIVING targeting)
- [ ] Create `backend/app/embeddings/identity.py`
  - [ ] `build_identity_text(name: str, substance: str, element: str | None, tags: list[str], visual_description: str) -> str` — constructs the identity string for embedding. Format: `"{name} — {substance} {element?} {visual_description}"`
  - [ ] `compute_object_embeddings(blueprint: CreatorOutputV2) -> tuple[list[float], list[list[float]]]` — returns (identity_embedding, list of behavior_target_embeddings). One batched API call.
- [ ] Create `backend/app/embeddings/trait_embeddings.py`
  - [ ] `TRAIT_STATE_TEXTS: dict[Tag, str]` — the ~10 trait-state descriptions (HEAT_SOURCE → "burning, on fire, aflame", etc.)
  - [ ] `compute_trait_embeddings() -> dict[Tag, list[float]]` — embed all trait-state texts once. Call at startup or lazy-init.
  - [ ] Store as module-level cached dict
- [ ] Unit tests in `backend/tests/test_embeddings.py`
  - [ ] `build_identity_text` produces expected format
  - [ ] `compute_object_embeddings` returns correct dimensions (768)
  - [ ] Spot check: dot product of donut identity vs "food, especially donuts" target > 0.5
  - [ ] Spot check: dot product of donut identity vs "criminals and lawbreakers" target < 0.3
  - [ ] Spot check: dot product of HEAT_SOURCE trait embedding vs "fires and burning things" > 0.5

### 8. Creator Agent V2

- [ ] Create `backend/app/creator/agent_v2.py`
  - [ ] New `SYSTEM_PROMPT_V2` (~80 lines) with three-menu structure:
    - Substance list with one-line descriptions (16 options)
    - Element list with one-line descriptions (7 options, pick 0-1)
    - Tag list with one-line descriptions (~10 options, pick 0-3)
    - Behavior verb descriptions (6 verbs, pick 0-4 with freeform target)
    - Visual descriptor guidance (unchanged from V1)
    - 3-4 examples: fire sword, cop, campfire, rubber duck
  - [ ] New PydanticAI agent using `CreatorOutputV2` as output type
  - [ ] Reuse `_build_model()` and model routing from V1 agent
  - [ ] `create_object_v2(description: str) -> GameObjectBlueprintV2`:
    1. Run LLM agent → `CreatorOutputV2`
    2. `derive_traits()` → internal trait list
    3. `resolve_substance_profile()` → numeric profile
    4. `compute_combat_profile()` → pre-computed coefficients
    5. `compute_object_embeddings()` → identity + behavior embeddings (can run parallel with step 2-4)
    6. Assemble `GameObjectBlueprintV2` with backward-compatible tags + V1 behaviors
    7. Return blueprint

### 9. Router Integration

- [ ] Update `backend/app/routers/objects.py`
  - [ ] Replace `create_object()` call with `create_object_v2()`
  - [ ] Blueprint JSON response includes all new fields (substance_profile, combat_profile, embeddings) — Godot client ignores unknown fields
  - [ ] Sprite generation unchanged (still uses visual_descriptor)

### 10. Implied Behaviors

- [ ] Update `backend/app/models/tag_behaviors.py` (or create `implied_behaviors_v2.py`)
  - [ ] `resolve_implied_behaviors_v2(tags: list[Tag], explicit_behaviors: list[BehaviorVerbSpec]) -> list[BehaviorVerbSpec]`
    - `LIVING` with no behaviors → add `investigate → "interesting nearby objects"` (default wander)
    - `LIVING` with `destroy` verb → add `flee → "overwhelming threats"` (survival instinct)
    - `EXPLOSIVE` → add `destroy → "self"` on damage (detonate) — or handle via existing implied behavior system
  - [ ] Convert V2 BehaviorVerbSpecs to V1 Behavior objects for Godot backward compat:
    - destroy → `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING` + HOSTILE tag (approximate)
    - eat → `ALWAYS -> MOVE_TOWARD -> NEAREST_LIVING` (approximate)
    - flee → `ON_DAMAGED -> MOVE_AWAY -> NEAREST_LIVING` (approximate)
    - investigate → `ALWAYS -> PATROL -> SELF` (approximate)
    - follow → `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER` (approximate)
    - protect → `ALWAYS -> MOVE_TOWARD -> NEAREST_PLAYER` (approximate)

### 11. Eval Adaptation

- [ ] Create `backend/evals/cases_v2.py` or update `cases.py`
  - [ ] Add expected substance + element to existing test cases (at least 20 key cases)
  - [ ] Example: "fire sword" → expected substance: metal, expected element: burning, expected tags: [SHARP]
  - [ ] Example: "rock" → expected substance: stone, expected element: null, expected tags: []
  - [ ] Example: "acid spider" → expected substance: flesh, expected element: acidic, expected tags: [LIVING]
- [ ] Add eval metrics
  - [ ] Substance accuracy: does V2 pick the expected substance?
  - [ ] Element accuracy: does V2 pick the expected element?
  - [ ] Tag precision/recall against the reduced tag set
  - [ ] Behavior quality (LLM judge): are verb+target pairs reasonable?
  - [ ] Backward compat: do V2-derived internal traits match V1 expected tags?
- [ ] Run V1 and V2 agents on overlapping cases, compare

### 12. Integration Test

- [ ] End-to-end test: POST `/api/sessions/{id}/objects`
  - [ ] Verify response includes substance_profile, combat_profile, identity_embedding
  - [ ] Verify response includes backward-compatible tags (existing Godot client can consume it)
  - [ ] Verify sprite generation still works (visual_descriptor unchanged)
  - [ ] Verify session persistence works (new blueprint fields stored/restored)

---

## Verification Criteria (Stage 1 done when)

- [ ] `make test` passes
- [ ] V2 agent produces valid blueprints for 20+ test objects
- [ ] V2-derived traits match V1 expected tags for >80% of eval cases
- [ ] Substance accuracy >90% on eval cases
- [ ] Embedding dot products pass spot checks (donut↔food high, donut↔criminals low)
- [ ] Existing Godot client works unchanged with V2 blueprints (backward-compatible tags + V1 behaviors)
- [ ] `make check` (lint + typecheck + test) passes
