# Architecture

## System Overview

```
Godot 4 Client                          FastAPI Backend
┌──────────────────┐                   ┌──────────────────────────┐
│ ObjectCreationPanel                  │                          │
│   └─ Backend.create_object() ──POST──►  /api/sessions/{id}/objects │
│                                      │    └─ PydanticAI agent ─────► Gemini LLM
│ Backend (autoload)                   │      (substance+element  │
│   ├─ HTTP client ◄─── JSON ─────────┤       +tags+behaviors)   │
│   └─ WebSocket  ◄── sprite_ready ───┤  Background task ────────────► Gemini image gen
│                                      │    └─ rembg / birefnet  │
│ RuleEngine (autoload)                │                          │
│   └─ mirrors backend rules           │  Ollama (local)          │
│                                      │    └─ qwen3-embedding    │
│ CollisionResolver (autoload)         │  aiosqlite               │
│   └─ EffectExecutor                  │    └─ sessions, objects  │
│                                      │                          │
│ GameObject                           │                          │
│   ├─ VerbBehaviorSystem (child node) │                          │
│   │    └─ embedding dot-product      │                          │
│   └─ TagField (child node, optional) │                          │
│        └─ FieldConfig                │                          │
└──────────────────┘                   └──────────────────────────┘
```

## EventBus Signals

`autoloads/event_bus.gd` — all signals:

| Signal | Arguments | Purpose |
|--------|-----------|---------|
| `interaction_triggered` | source_name, source_tags, target_name, target_tags, effect_message, world_pos | Rule engine collision result (HUD feedback) |
| `object_created` | blueprint: Dictionary | Backend returned blueprint; triggers placement flow |
| `sprite_ready` | object_id: String, texture: Texture2D | Decoded sprite available |
| `sprite_failed` | object_id: String | Sprite generation failed; proceed to placement without texture |
| `level_completed` | level_id: int | Level win condition met |
| `creation_requested` | — | Player submitted description; start materialize effect |
| `creation_failed` | — | Backend rejected creation; cancel effect |
| `placement_started` | — | Ghost preview active, awaiting click |
| `placement_ended` | — | Placement confirmed or cancelled |
| `debug_toggled` | enabled: bool | Debug overlay visibility changed |
| `player_died` | — | Player death event |
| `player_damaged` | amount: float, current: int, maximum: int | Player took damage (drives HUD health bar) |
| `player_healed` | amount: float, current: int, maximum: int | Player healed |
| `effect_applied` | effect_type: String, amount: float, element_color: Color, world_pos: Vector2 | Visual effect feedback (floating numbers, etc.) |
| `object_entered_scene` | game_object: Node | Object added to world — VerbBehaviorSystem listens to score candidates |
| `object_exited_scene` | game_object: Node | Object removed from world — VerbBehaviorSystem cleans target lists |
| `object_embedding_changed` | game_object: Node | Object's identity embedding updated (tag change) — triggers re-score |

## Object Creation Pipeline

Full flow from player input to world-placed object with sprite:

1. **Player types description** → `ObjectCreationPanel` sends text to `Backend.create_object()`
2. **HTTP POST** → `POST /api/sessions/{id}/objects` with `{"description": "..."}`
3. **Budget reserve** → `SessionManager.reserve_budget()` atomically charges $0.041 upfront (rejects with 402 if budget exceeded)
4. **LLM agent** → `creator.agent.create_object()` runs PydanticAI agent (3 retries). Produces `CreatorOutput`: name (1-3 words), substance (1 of 16), element (0-1 of 7), tags (0-3 from `LLM_VISIBLE_TAGS_V2`), behaviors (0-4 `BehaviorVerbSpec`). Falls back to stone + no element + no tags on failure
5. **Trait derivation** → `derive_traits(substance, element, tags, verbs)` merges `SUBSTANCE_AUTO_TRAITS` + `ELEMENT_TRAITS` + explicit tags + behavior-derived (destroy → HOSTILE)
6. **Profile resolution** → `resolve_profile()` applies element overrides + tag modifiers to `SUBSTANCE_PROFILES[substance]` → final `SubstanceProfile` (mass, friction, bounce, gravity, damping, etc.). `compute_combat_profile()` derives melee/crush damage coefficients
7. **Embedding** → `compute_object_embeddings()` batches identity string + all behavior target strings via Ollama `qwen3-embedding:0.6b` → 1024-dim vectors. Zero vectors if Ollama unavailable
8. **Blueprint construction** → `GameObjectBlueprint` assembled with UUID, full trait list, serialized `substance_profile`, `combat_profile`, `identity_embedding`, `behavior_embeddings`, `starting_durability` (from profile)
9. **Persist** → `save_object()` saves blueprint to `objects` table (`blueprint_json` column)
10. **Immediate response** → Client receives blueprint JSON + `budget_remaining`. `EventBus.creation_requested` was emitted on submit — `Game` starts a `MaterializeEffect` at spawn point
11. **Background sprite generation** → `asyncio.Task` held in module-level `_background_tasks` set (prevents GC). Runs image pipeline (see below)
12. **WebSocket delivery** → `send_sprite_ready()` broadcasts `{sprite_url}` to all session clients → Godot fetches PNG → decodes to `ImageTexture` → `EventBus.sprite_ready` emitted
13. **Placement mode** → On `sprite_ready` (or `sprite_failed`), ghost preview follows mouse; left-click spawns. Object NOT added to world until placement confirmed

`EventBus.creation_failed` cancels the effect and discards the pending blueprint at any point in the flow.

## Image Generation Pipeline

`images/pipeline.py` — cache-first sprite generation:

```
1. Cache check    → static/sprites/{hash}.png exists? Return cached URL
                     (skipped entirely if SPRITE_CACHE_ENABLED=false)
2. Prompt build   → build_prompt(name, visual_descriptor):
                     "mixed media collage style paper cutout, side view, flat lighting,
                      clean edges, {name}, {visual_description},
                      single centered object, contrasting solid background color, no text"
3. Image generate → selected backend (IMAGE_BACKEND):
                     gemini: Gemini image gen via IMAGE_MODEL
                     local:  SGLang FLUX server (LOCAL_IMAGE_URL)
                     fal:    fal.ai FLUX
4. Remove bg      → local GPU PyTorch (BG_REMOVAL_MODEL, default briaai/RMBG-2.0)
                     or cloud fal.ai/birefnet (BG_REMOVAL_BACKEND=cloud)
5. Crop & fit     → LANCZOS resize to fill 90% of a 512×512 canvas (TEXTURE_RESOLUTION).
                     World display size is determined client-side by size_category.
6. Cache write    → PNG saved to static/sprites/{hash}.png
                     (skipped if SPRITE_CACHE_ENABLED=false)
```

**Cache key**: SHA-256 of the full prompt string (`build_prompt` output), truncated to 16 hex chars. Identical prompts share a cached sprite regardless of which object requested them.

**`SPRITE_CACHE_ENABLED`**: Boolean env var (default `true`). When `false`, cache reads and writes are both skipped — every request hits Gemini.

**Concurrency**: Semaphore-limited to `MAX_CONCURRENT_IMAGE_REQUESTS` (default 3).

**`generate_sprite(blueprint, remove_bg)`**: Takes a `GameObjectBlueprint` directly. Builds prompt from `blueprint.name` + `blueprint.visual_descriptor`.

## Rule Engine

### Backend: `engine/resolver.py`

`RuleResolver` builds a two-tier index at init from 59 `InteractionRule` definitions:

**Pair index** (O(1) lookup): Nested dict `tag_a → tag_b → [rules]`. For bidirectional rules, both `(a,b)` and `(b,a)` entries are created.

**Wildcard rules** (O(n) scan, n ≈ 3-5): Rules where `tags_required_b` is empty. Match when `tags_required_a ⊆ tags_a` (or `⊆ tags_b` if bidirectional).

**Matching algorithm** (`find_matching_rules`):
1. For each tag pair `(ta, tb)` where `ta ∈ tags_a` and `tb ∈ tags_b`: check pair index, verify full tag subset inclusion
2. Scan wildcard rules for subset matches
3. Deduplicate by `rule_id`, sort by `execution_order` descending

**`TriggerMode`** (`models/rules.py`): StrEnum — `CONTACT` (default) | `FIELD`. ~28 of 59 rules are annotated `trigger_mode=TriggerMode.FIELD`. FIELD rules also fire on contact — `trigger_mode` is purely a filter used client-side by `TagField` and `CollisionResolver.resolve_collision(trigger_mode_filter=...)`.

### Godot: `autoloads/rule_engine.gd`

Mirrors the backend resolver. Rules are loaded from session response JSON (`Backend.create_session()` or `Backend.restore_session()`). Same two-tier index, same matching logic. Exists so collision resolution doesn't require a server round-trip.

## Field System

Distance-based and continuous tag interactions. Objects with field-emitting tags affect nearby objects without requiring direct collision.

### Design split: rules declare mode, tags declare range

`InteractionRule.trigger_mode = FIELD` declares that an interaction works at distance. `FieldConfig` (per-tag) declares *how far* and *how* (continuous or periodic). This prevents duplicating range values across rules that share the same emitting tag.

### FieldConfig (`godot/scripts/data/field_config.gd`)

Static class. Maps field-emitting tags to range category and mode:

| Tag | Range | Mode |
|-----|-------|------|
| WIND_SOURCE | FAR (192px) | continuous |
| MAGNETIC | MEDIUM (96px) | continuous |
| STICKY | CLOSE (64px) | continuous (damp, not force) |
| HEAT_SOURCE | CLOSE (64px) | periodic |
| HOT | CLOSE (64px) | periodic |
| ELECTRIC | CLOSE (64px) | periodic |
| COLD | CLOSE (64px) | periodic |
| TOXIC | MEDIUM (96px) | periodic |
| LIQUID | CLOSE (64px) | periodic |
| HOSTILE | CLOSE (64px) | periodic |
| WET | CLOSE (64px) | periodic |

`PERIODIC_INTERVAL = 2.0s`. Range categories: CLOSE=64px, MEDIUM=96px, FAR=192px.

### TagField (`godot/scripts/systems/tag_field.gd`)

Node child of `GameObject` (same lifecycle pattern as `VerbBehaviorSystem`). Created when field tags are present:

```
init_from_blueprint()
  └─ FieldConfig.has_any_field_tag(tags)? → _create_tag_field()
       └─ TagField.init_field(owner, tags) → _rebuild(tags)

add_tag(tag)  [dynamic, e.g. fire spread adds HEAT_SOURCE]
  └─ _tag_field != null → on_tags_changed(tags)
     else → FieldConfig.has_any_field_tag(tags)? → _create_tag_field()
```

**`_rebuild(tags)`**:
1. Collects current field tags; short-circuits if unchanged
2. Pre-caches continuous FIELD rules via `RuleEngine.find_matching_rules()` → `_cached_continuous`
3. Creates/resizes one Area2D (CircleShape2D) at max range across all field tags
4. Manages periodic Timer (reuse if exists; first tick fires immediately via `call_deferred`)
5. Toggles `_physics_process` and `can_sleep` based on whether continuous fields are present

**Continuous mode** (`_physics_process`): For each body overlapping the Area2D, applies `APPLY_FORCE` effects from pre-cached continuous rules directly via `apply_central_force()`. Per-tag center-to-center distance check (1.5× range margin to account for shape overlap).

**Periodic mode** (`_on_periodic_tick`): Every 2s, calls `CollisionResolver.resolve_collision(owner, body, 0, "FIELD")` for each overlapping body in range. The `"FIELD"` filter makes `CollisionResolver` skip CONTACT-only rules. Per-chain dedup key includes the trigger mode suffix (`"id_a:id_b:FIELD"`) — FIELD and CONTACT interactions dedup independently, so a periodic field tick won't suppress a concurrent physical collision between the same pair.

**Detection geometry**: Shape-vs-shape Area2D overlap — accounts for object sizes automatically. One Area2D per field object at max range across all field tags (not one per tag).

### Cascade interaction with field

Field-ignited objects become new field sources. When a rule adds HEAT_SOURCE (e.g., ignition), `game_object.gd` lazy-creates a `TagField` on that object. Each field periodic tick starts at `cascade_depth=0`, allowing unbounded propagation over time. The depth-3 cap per tick prevents instant chain explosions — fire spreads one step per 2s period.

### STICKY slow field (`tag_field.gd`)

STICKY uses `TagField._apply_sticky_slow()` instead of joint-based pinning. Per physics frame, bodies within CLOSE range (64px) have `linear_damp` raised to `STICKY_DAMP=12.0` (tracked in `_sticky_damped` dict so original damping is restored on exit). The player receives `apply_speed_modifier(0.25)` — 25% speed — via duck-typed interface. Bodies and the player are restored when they leave the field or when the STICKY tag is removed. This approach is handled entirely within `TagField`; `CollisionResolver` has no STICKY-specific logic.

## Behavior System

Objects carry 0-4 behaviors expressed as verb + freeform target string. Behaviors are LLM-authored; only one implicit default exists (LIVING + no behaviors → investigate). Tags = what objects *are*; behaviors = what objects *do*.

### Data Model (`backend/app/models/blueprint.py`)

`BehaviorVerbSpec`: `verb: BehaviorVerb` + `target: str` (1-100 chars, freeform description of what to act on).

| Verb | Action |
|------|--------|
| `destroy` | Move toward + melee attack |
| `eat` | Move toward + consume (damage target, heal self) |
| `investigate` | Move toward slowly, stop at medium range |
| `follow` | Move toward, maintain close distance |
| `protect` | Follow target + attack threats near it |
| `flee` | Move away at high speed |

`resolve_implied_behaviors()`: if LIVING and no explicit behaviors, adds `investigate → "interesting nearby objects"`. No other defaults.

### Godot Runtime (`godot/scripts/systems/verb_behavior_system.gd`)

`VerbBehaviorSystem` is a Node child of `GameObject` when `behaviors` is non-empty. Two layers:

**Perception (event-driven)**:
- Listens to `EventBus.object_entered_scene` / `object_exited_scene` / `object_embedding_changed`
- On enter/embedding_changed: computes dot-product between behavior's target embedding and the object's identity embedding
- Objects with similarity ≥ `MATCH_THRESHOLD` (0.5) are added to that behavior's `_target_lists[i]`
- On exit: removed from all target lists

**Action (per physics frame)**:
- Walks behaviors in priority order (index 0 = highest)
- For first behavior with non-empty targets: finds nearest valid target, executes verb
- Returns after executing one verb per frame

**Error fallback**: disables entire system after 5 consecutive errors.

**Speed constants**: destroy=200, eat=180, investigate=80, follow=160, protect=180, flee=250 px/s. Melee range=48px, investigate stop range=128px, follow range=64px. Melee cooldown=1.0s.

**Embed re-scoring**: when an object's tags change, `game_object.gd` re-requests the identity embedding via `POST /api/embed` and emits `object_embedding_changed` — all `VerbBehaviorSystem` instances re-score that object against their behavior embeddings.

## Collision & Cascade System

`scripts/systems/collision_resolver.gd` — per-frame collision resolution:

```
body_entered signal (from GameObject)
  └─ call_deferred("_resolve_deferred", body)   # deferred to avoid physics flush crash
       └─ resolve_collision(body_a, body_b, cascade_depth=0, trigger_mode_filter="", _resolved={})
            ├─ Per-chain dedup: pair key "id_a:id_b:trigger_mode_filter" in _resolved → skip
            ├─ Top-level calls reset _resolved={}; cascades inherit parent's dict
            ├─ Extract tags: TagColors.get_body_tags() (duck-typed: effective_tags/get_tags)
            ├─ RuleEngine.find_matching_rules(tags_a, tags_b)
            ├─ Filter by trigger_mode_filter if non-empty (e.g., "FIELD" from TagField)
            ├─ Record tags_before snapshot
            ├─ For each matched rule: EffectExecutor.execute(rule, body_a, body_b)
            └─ Cascade check (if any rule was cascade_eligible):
            ├─ Compare tags_before vs tags_after
            └─ If changed: _cascade_to_neighbors(body, depth + 1, _resolved)
                 ├─ Prefer get_cascade_neighbors() (CascadeArea overlaps)
                 └─ Fallback: physics space query (CircleShape2D, 96px radius)
```

**Constants**: `MAX_CASCADE_DEPTH = 3`, `CASCADE_RADIUS = 96px`.

**Per-chain deduplication**: `_resolved` dict is passed through the entire cascade chain. The same pair (including trigger mode suffix) can't fire twice in one chain, preventing loops. Independent collisions (new `body_entered` events) each start with a fresh `_resolved` dict. FIELD and CONTACT interactions dedup independently — different key suffixes.

**`trigger_mode_filter`**: When `"FIELD"`, only rules with `trigger_mode == "FIELD"` are executed. Contact-originated calls pass `""` (no filter), so ALL rules (including FIELD) fire on contact.

**Behavior cascade**: When `VerbBehaviorSystem` mutates tags via `WorldMutations`, `CollisionResolver.resolve_collision()` is called at depth 1 for each neighbor if tags changed — starting at depth 1 avoids double-counting the mutation as a cascade origin.

### Effect Executor & World Mutations

`scripts/systems/effect_executor.gd` — 5 primitive effect types. Composite interactions (ignite, freeze, electrify, etc.) are expressed as arrays of these primitives in rule data.

| Effect | Key fields | Behavior |
|--------|-----------|----------|
| DAMAGE | `damage_amount`, `tick_interval`, `tick_duration` | Instant damage, or DOT if `tick_interval` > 0 |
| HEAL | `damage_amount` | Restore durability |
| ADD_TAG | `tag`, `tag_duration` | Add tag (permanent if `tag_duration` absent/0) |
| REMOVE_TAG | `tag` | Remove tag |
| APPLY_FORCE | `force_magnitude` | Impulse away from source body |

**DOT**: DAMAGE with `tick_interval`/`tick_duration` fields routes to `WorldMutations.apply_dot()`. Replaces any existing DOT on the target (named node `_dot_timer`) — no stacking. Replacement sequence: `stop()` → `remove_child()` → `queue_free()` — skipping `remove_child()` leaves the node in the tree until end-of-frame and causes Godot to auto-rename the new timer, breaking subsequent `get_node_or_null("_dot_timer")` lookups.

**Target resolution**: Effects specify `target: "a" | "b" | "both"`. Default is `"b"`.

**Rules serialization**: `model_dump(exclude_none=True)` keeps effect payloads lean — only fields relevant to the effect type are sent.

### WorldMutations

`scripts/systems/world_mutations.gd` — static `RefCounted` class. All game-state mutations (damage, heal, tag add/remove, impulse, DOT) route through it. Single codepath shared by `EffectExecutor`, `VerbBehaviorSystem`, `projectile.gd`, and level scripts. Guards against invalid targets with `has_method`/`is RigidBody2D` checks before acting.

`apply_add_tag()` auto-removes contradictory tags before adding by querying `TagContradictions.get_contradictions()`. For example, adding HEAT_SOURCE removes WET first. This mirrors the backend's `TAG_CONTRADICTIONS` list at runtime.

### TagDecay

`scripts/systems/tag_decay.gd` — Node child shared by `GameObject` and `EnvironmentBody`. Manages per-tag decay timers. `set_decay(tag, duration)` starts a one-shot timer; `cancel(tag)` clears it. On expiry, calls `get_parent().remove_tag(tag)`. Previously the decay logic was duplicated in both host classes; `TagDecay` extracts it.

### TagColors (utilities)

`scripts/data/tag_colors.gd` also contains three static utility functions used system-wide:
- `get_body_tags(body)` — duck-typed: calls `get_effective_tags()` (player), `get_tags()` (objects/env), or returns `[]`
- `derive_element_color(body)` — returns first tag color from `COLORS` dict, or white
- `is_taggable(body)` — `true` if body has either tag-accessor method

## EnvironmentBody

`scenes/environment_body/environment_body.gd` — `StaticBody2D`-based tagged environment hazard (acid pools, fire pits, electric fences, etc.).

**Duck-typed interface** (participates in the rule engine without modification to CollisionResolver or WorldMutations):

| Method | Present | Effect |
|--------|---------|--------|
| `get_tags()` | Yes | Rule engine reads tags |
| `get_object_id()` | Yes | Pair cooldown keying |
| `add_tag(tag, duration)` | Yes | Tag mutations (freeze, ignite, etc.) |
| `remove_tag(tag)` | Yes | Tag removal |
| `take_damage()` | **No** | Indestructible — WorldMutations skips damage |
| `heal()` | **No** | Same |

**Solidity parameter** (`solid: bool`):

| Mode | `collision_layer` | Periodic tick filter | Use case |
|------|-------------------|----------------------|----------|
| `solid=false` | 0 (passthrough) | `""` — ALL rules fire | Acid pools, lava, toxic gas |
| `solid=true` | OBJECTS layer | `"FIELD"` — FIELD-only | Electric fences, walls |

Non-solid uses no filter because being inside the substance is semantically equivalent to contact — CONTACT rules must fire. Solid already receives CONTACT rules via `body_entered` on colliding RigidBody2D objects, so periodic ticks add only FIELD rules.

**Field detection**: Owns a rectangular `Area2D` (`FieldArea`) sized to body dimensions + 32px margin. This replaces `TagField` because `TagField`'s circular shape is too small for large env bodies. Handles its own periodic timer (2s interval, first tick deferred) — only created/active when `FieldConfig.has_any_field_tag(tags)` is true, same lifecycle as `TagField`.

**Tag reactivity**:
- FROZEN → `collision_layer` promoted to OBJECTS (non-solid becomes walkable frozen surface); visual tinted blue-white. Reverts when FROZEN removed.
- Periodic timer created/destroyed dynamically as field tags are added/removed (same as `TagField._rebuild()`).
- Temporary tags: managed by a `TagDecay` child node (shared pattern with `game_object.gd`) — `TagDecay.set_decay(tag, duration)` / `cancel(tag)`.

**Level creation helpers** (all on `BaseLevel`):
- `_create_env_body(pos, size, tags, color, id, solid)` — pos is top-left corner, body positioned at `pos + size/2` (same convention as `_create_platform`)
- `_spawn_game_object(blueprint, pos) -> Node` — instantiate `game_object.tscn`, add_child, position, `init_from_blueprint`
- `_create_kill_zone(pos, size)` — `Area2D` on HAZARDS layer; respawns player, deals 999 dmg to objects

**Player detection**: Player is `CharacterBody2D` using `move_and_slide()`, which doesn't trigger `body_entered` on other bodies. The env body's own `FieldArea` (mask includes PLAYER layer) handles player detection and routes through `CollisionResolver.resolve_collision()`.

## Physics Composition

V2: physics is pre-computed on the backend from the substance profile and stored in `blueprint.substance_profile`. The Godot client reads it directly — no tag-to-physics lookup table.

**Pipeline**: `resolve_profile(substance, element, tags)` in `engine/trait_deriver.py` → serialized into `blueprint.substance_profile` dict → `SubstancePhysics.resolve_physics(blueprint)` in Godot → `PhysicsApplicator.apply_from_blueprint(bp)`.

**State-derived defaults** (applied when profile fields are sentinel -1.0):

| State | Gravity | Damping |
|-------|---------|---------|
| solid | 1.0 | 0.5 |
| liquid | 1.0 | 2.0 |
| gas | -0.2 | 4.0 |
| energy | 0.0 | 0.0 |

**Tag modifiers applied in `resolve_profile()`**:
- HEAVY: mass += 5.0, friction = max(friction, 0.7)
- LIGHT: mass × 0.15, damping = 1.5
- BREAKABLE: durability × 0.4
- BOUNCY: bounce = 0.9, friction = min(friction, 0.2)
- STICKY: friction = max(friction, 2.0), bounce = 0.0
- FLYING: gravity = 0.0, damping = 2.0

**Final mass** = `substance_profile.mass × size_mass_multiplier`. Size multipliers: tiny=0.25×, small=0.5×, medium=1.0×, large=4.0×, huge=10.0×.

**Sprite-driven collision shape**: Pre-sprite fallback is a rectangle sized from `size_category` via `PhysicsComposer.get_size_data()`. When a real sprite loads, `ObjectVisual.set_sprite()` calls `PhysicsApplicator.update_shape_from_sprite()` via `call_deferred`. That method reads the texture's opaque bounding rect (`Image.get_used_rect()`), replaces the `CollisionShape2D` with a `RectangleShape2D` sized to the opaque region, and offsets it to match the sprite's visual center. Once set, `_has_sprite_shape = true` prevents subsequent tag mutations from overwriting the shape.

## Session & Persistence

### SQLite Schema (2 tables, initialized in `main.py` lifespan)

| Table | Key | Fields |
|-------|-----|--------|
| `sessions` | `id TEXT PK` | created_at, budget_used, budget_limit (default $1.00) |
| `objects` | `(session_id, object_id) PK` | blueprint_json, x, y, durability |

`blueprint_json` stores the full `GameObjectBlueprint` including V2 fields (`substance_profile`, `combat_profile`, `identity_embedding`, `behavior_embeddings`).

### Session Lifecycle

1. **Create** (`POST /api/sessions`): New UUID, empty session. Response includes all rules and WebSocket URL. Seed objects are defined client-side in level scripts, not persisted at session creation
2. **Restore** (`GET /api/sessions/{id}`): Full load — session row + objects
3. **Sync** (`PUT /api/sessions/{id}/sync`): Partial update — only provided fields are written. Client syncs every 10s via `Backend._on_sync_timer()` when `_state_dirty` flag is set

### Budget Tracking

$0.041 per object creation (LLM ~$0.001 + image ~$0.04). Default session budget: $1.00 (~24 objects). `track_cost_and_save_object()` atomically updates `budget_used` and saves the object in one commit.

## WebSocket Protocol

Endpoint: `ws://{host}/ws/{session_id}`. Session must exist or connection is rejected (close code 4004).

**Per-session broadcast**: `_connections: dict[session_id → set[WebSocket]]`. All messages sent to every connected client.

| Direction | Type | Payload |
|-----------|------|---------|
| Client → Server | `ping` | — |
| Client → Server | `request_sprite` | `object_id` — re-request cached sprite (used on reconnect) |
| Server → Client | `pong` | — |
| Server → Client | `sprite_ready` | `object_id`, `sprite_url` |
| Server → Client | `sprite_failed` | `object_id`, `reason` |
| Server → Client | `error` | `message` |

**Godot reconnect**: Exponential backoff from 1s to 30s max. On reconnect, re-requests pending sprites via `request_sprite`. Server checks cache on disk and re-sends `sprite_ready` if found — recovers sprites lost during API reload or disconnect.
