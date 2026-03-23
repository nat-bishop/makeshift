# Architecture

## System Overview

```
Godot 4 Client                          FastAPI Backend
┌──────────────────┐                   ┌──────────────────────────┐
│ ObjectCreationPanel                  │                          │
│   └─ Backend.create_object() ──POST──►  /api/sessions/{id}/objects │
│                                      │    └─ PydanticAI agent ─────► Gemini LLM
│ Backend (autoload)                   │    └─ placeholder PNG ◄──┘  │
│   ├─ HTTP client ◄─── JSON ─────────┤      (tags + behaviors)  │
│   └─ WebSocket  ◄── sprite_ready ───┤  Background task ────────────► Flux (fal.ai)
│                                      │    └─ rembg / birefnet  │
│ RuleEngine (autoload)                │                          │
│   └─ mirrors backend rules           │  aiosqlite               │
│                                      │    └─ sessions, objects  │
│ CollisionResolver (autoload)         │                          │
│   └─ EffectExecutor                  │                          │
│                                      │                          │
│ GameObject                           │                          │
│   └─ BehaviorExecutor (child node)   │                          │
│        └─ BehaviorMaps               │                          │
└──────────────────┘                   └──────────────────────────┘
```

## Object Creation Pipeline

Full flow from player input to world-placed object with sprite:

1. **Player types description** → `ObjectCreationPanel` sends text to `Backend.create_object()`
2. **HTTP POST** → `POST /api/sessions/{id}/objects` with `{"description": "..."}`
3. **Budget check** → `SessionManager.get_budget_info()` verifies remaining budget (rejects with 402 if exhausted)
4. **LLM agent** → `creator.agent.create_object()` runs PydanticAI agent (Gemini 3.1 Flash Lite Preview, 3 retries). Validators enforce: 1-3 word name, 2-6 tags, no contradictions, tag budget ≤ 10, 0-3 behaviors, behavior budget ≤ 6. Falls back to generic "Mysterious {description}" on failure
5. **Blueprint construction** → `GameObjectBlueprint` adds UUID, computed fields: `power_cost`, `behavior_cost`, `starting_durability`
6. **Atomic persist** → `track_cost_and_save_object()` charges $0.041 + saves blueprint (including behaviors) in one commit
7. **Immediate response** → Client receives blueprint JSON (with behaviors) + placeholder PNG (colored rounded rectangle) + budget_remaining
8. **Background sprite generation** → `asyncio.Task` held in module-level `_background_tasks` set (prevents GC). Runs image pipeline (see below)
9. **WebSocket delivery** → `send_sprite_ready()` broadcasts base64 PNG to all session clients → Godot decodes to `ImageTexture` → `EventBus.sprite_ready` emitted → `ObjectVisual` updates

## Image Generation Pipeline

`images/pipeline.py` — cache-first sprite generation:

```
1. Cache check    → static/sprites/{hash}.png exists? Return cached bytes
2. Prompt build   → "pixel art game sprite, side view, {size} {base_form} made of {material},
                     {color_primary_name} with {color_secondary_name} accents, {effects},
                     solid {bg_color} background, no text"
3. Flux generate  → fal.ai Flux Pro Kontext, 512×512 default
4. Remove bg      → local rembg (birefnet-general model, alpha matting)
                     or cloud fal.ai/birefnet (configured via BG_REMOVAL_BACKEND)
5. Resize         → LANCZOS to target size from SIZE_PIXEL_MAP:
                     tiny=32, small=48, medium=64, large=96, huge=128
6. Cache write    → PNG saved to static/sprites/{hash}.png
```

**Cache key**: SHA-256 of `base_form|material|color_primary_name|color_secondary_name|sorted_effects|size_category|bg_color`, truncated to 16 hex chars.

**Concurrency**: Semaphore-limited to `MAX_CONCURRENT_IMAGE_REQUESTS` (default 3).

**Placeholder generation**: `generate_placeholder()` creates a colored rounded rectangle using the first matching tag color from `TAG_COLOR_MAP` (15 tags have mapped colors) or the descriptor's primary color.

## Rule Engine

### Backend: `engine/resolver.py`

`RuleResolver` builds a two-tier index at init from 43 `InteractionRule` definitions:

**Pair index** (O(1) lookup): Nested dict `tag_a → tag_b → [rules]`. For bidirectional rules, both `(a,b)` and `(b,a)` entries are created.

**Wildcard rules** (O(n) scan, n ≈ 3-5): Rules where `tags_required_b` is empty. Match when `tags_required_a ⊆ tags_a` (or `⊆ tags_b` if bidirectional).

**Matching algorithm** (`find_matching_rules`):
1. For each tag pair `(ta, tb)` where `ta ∈ tags_a` and `tb ∈ tags_b`: check pair index, verify full tag subset inclusion
2. Scan wildcard rules for subset matches
3. Deduplicate by `rule_id`, sort by priority descending

### Godot: `autoloads/rule_engine.gd`

Mirrors the backend resolver. Rules are loaded from session response JSON (`Backend.create_session()` or `Backend.restore_session()`). Same two-tier index, same matching logic. Exists so collision resolution doesn't require a server round-trip.

## Behavior System

Objects carry 0-3 autonomous behaviors defined at creation time. Tags = what objects *are*; behaviors = what objects *do*. The two systems are additive and independent.

### Data Model (`backend/app/models/behaviors.py`)

Each `Behavior` is a flat Pydantic record:

| Field | Type | Values |
|-------|------|--------|
| `trigger` | `BehaviorTrigger` | ALWAYS, ON_TIMER, ON_PROXIMITY, ON_CONTACT, ON_DAMAGED, ON_HEALTH_LOW, ON_TAG_ADDED, ON_CREATE, ON_DESTROY, ON_USE |
| `action` | `BehaviorAction` | MOVE_TOWARD, MOVE_AWAY, PATROL, DEAL_DAMAGE, APPLY_FORCE, ATTRACT, SPAWN_PROJECTILE, EXPLODE, HEAL, ADD_TAGS, REMOVE_TAGS, SELF_DESTRUCT |
| `target` | `BehaviorTarget` | SELF, NEAREST_OBJECT, NEAREST_LIVING, NEAREST_PLAYER, CONTACT_BODY |
| `condition` | `BehaviorCondition \| None` | Optional gate: HAS_TAG, NOT_HAS_TAG, TARGET_HAS_TAG |
| `intensity` | `Intensity` | MINIMAL, LOW, MEDIUM, HIGH, EXTREME (default MEDIUM) |
| `range` | `BehaviorRange` | TOUCH, CLOSE, MEDIUM, FAR (default MEDIUM) |
| `speed` | `Speed` | SLOW, MEDIUM, FAST, VERY_FAST (default MEDIUM) |
| `interval` | `Interval` | ONCE_SHORT, ONCE_MEDIUM, ONCE_LONG, SLOW, MEDIUM, FAST (default MEDIUM) |
| `message` | `str \| None` | Optional player-facing string (max 60 chars), emitted via EventBus |
| `tags_to_apply` | `list[Tag] \| None` | Required for ADD_TAGS/REMOVE_TAGS |
| `trigger_tag` | `Tag \| None` | Required for ON_TAG_ADDED — which tag to watch |

### Budget

- Behavior budget: 6 per object (separate from tag budget of 10)
- `cost = max(floor, action_base_cost + intensity_modifier)`
- Action costs: SELF_DESTRUCT=1, most actions=2, SPAWN_PROJECTILE/EXPLODE=3
- Intensity modifiers: MINIMAL=-1, LOW/MEDIUM=0, HIGH=+1, EXTREME=+2
- SPAWN_PROJECTILE and EXPLODE have a cost floor of 2
- Enforced by `check_behavior_budget` field validator on `CreatorOutput` (raises `ModelRetry`)

### Godot Runtime (`godot/scripts/systems/behavior_executor.gd`)

`BehaviorExecutor` is a Node attached as a child of `GameObject` when `behaviors` is non-empty. Lifecycle:

```
init_from_blueprint()
  └─ behaviors present? → instantiate BehaviorExecutor → add_child → init_behaviors()
       ├─ ON_TIMER behaviors → setup Timer nodes
       └─ ON_CREATE behaviors → execute immediately

_physics_process(delta)
  ├─ Update target cache every 0.3s (NEAREST_* targets)
  ├─ Collect triggered behaviors: ALWAYS, ON_PROXIMITY (distance check), ON_HEALTH_LOW
  ├─ Sort by TRIGGER_PRIORITY (movement conflict resolution)
  └─ Execute behaviors:
       ├─ Non-movement: always execute (subject to cooldown)
       └─ Movement (MOVE_TOWARD/MOVE_AWAY/PATROL): only highest-priority trigger wins per frame

fire_trigger(trigger_name, event_body)  # called by GameObject on events
  └─ ON_CONTACT, ON_DAMAGED, ON_DESTROY → direct dispatch

on_tag_added(tag)  # called by GameObject.add_tag()
  └─ ON_TAG_ADDED → dispatch if trigger_tag matches
```

**Error fallback**: `BehaviorExecutor` tracks consecutive action failures. After 3 consecutive errors it sets `_disabled = true` — the executor stops processing permanently.

**Movement uses `apply_central_force()`** with velocity clamping against `BehaviorMaps.SPEED_MAX`. This composes with existing `PhysicsApplicator` mass/friction/gravity settings.

**Cooldown**: All non-ALWAYS, non-ON_CREATE, non-ON_DESTROY triggers respect a per-behavior cooldown keyed by `interval`. ONCE_* intervals use one-shot timers that prevent re-firing.

### Categorical → Numeric Mapping (`godot/scripts/data/behavior_maps.gd`)

`BehaviorMaps` is a static `RefCounted` class (not an autoload) with constants mapping string tier names to engine values:

| Map | Example values |
|-----|---------------|
| `INTENSITY_DAMAGE` | MINIMAL=5, MEDIUM=20, EXTREME=80 |
| `INTENSITY_FORCE` | MINIMAL=50, MEDIUM=200, EXTREME=800 |
| `INTENSITY_HEAL` | MINIMAL=5, MEDIUM=25, EXTREME=100 |
| `INTENSITY_EXPLODE` | MINIMAL=10, MEDIUM=40, EXTREME=150 |
| `RANGE_PX` | TOUCH=32, CLOSE=64, MEDIUM=128, FAR=256 |
| `SPEED_MAX` | SLOW=60, MEDIUM=120, FAST=200, VERY_FAST=300 |
| `SPEED_FORCE` | SLOW=200, MEDIUM=400, FAST=600, VERY_FAST=800 |
| `INTERVAL_SECONDS` | ONCE_SHORT=1.0, ONCE_MEDIUM=3.0, SLOW=3.0, MEDIUM=1.5, FAST=0.75 |
| `TRIGGER_PRIORITY` | ON_HEALTH_LOW=1 … ALWAYS=7 (lower = higher priority) |
| `PAYLOAD_TAG_MAP` | HEAT_SOURCE→HOT, ELECTRIC→ELECTRIC, TOXIC→TOXIC, CORROSIVE→CORROSIVE, FROZEN→COLD |

### Projectile System (`godot/scenes/projectile/`)

`SPAWN_PROJECTILE` action spawns a `RigidBody2D` projectile scene. Properties:
- Base tags: `[SOLID, LIGHT, BREAKABLE]` plus one payload tag inherited from parent (via `PAYLOAD_TAG_MAP`)
- Gravity scale 0 (straight-line flight), speed 250 px/s, lifetime 2.5s auto-destroy
- On contact: deals damage directly, then calls `CollisionResolver.resolve_collision()` so payload tag participates in rule engine (e.g., HOT projectile ignites FLAMMABLE target)
- Ignores its source object to prevent self-hit

### Integration with Tags and Rules

`ON_TAG_ADDED` is the key bridge between the rule engine and the behavior system:

```
Object A (HEAT_SOURCE) collides with Object B (EXPLOSIVE)
  └─ RuleEngine matches: HEAT_SOURCE + EXPLOSIVE → ADD_TAG(HOT) on B
       └─ B.add_tag("HOT") → BehaviorExecutor.on_tag_added("HOT")
            └─ Behavior: ON_TAG_ADDED(HOT) → EXPLODE
```

`ADD_TAGS` / `REMOVE_TAGS` behavior actions trigger cascade: after mutating tags, `CollisionResolver.resolve_collision()` is called on the target's neighbors, propagating rule engine interactions.

Direct `DEAL_DAMAGE` from behaviors bypasses the rule engine — no double-dipping with collision rules.

## Collision & Cascade System

`scripts/systems/collision_resolver.gd` — per-frame collision resolution:

```
body_entered signal (from GameObject.body_entered)
  └─ resolve_collision(body_a, body_b, cascade_depth=0)
       ├─ Cooldown check: pair key "id_a:id_b" (sorted), skip if < 0.5s
       ├─ Extract tags: get_effective_tags() (player) or get_tags() (object)
       ├─ RuleEngine.find_matching_rules(tags_a, tags_b)
       ├─ Record tags_before snapshot
       ├─ For each matched rule: EffectExecutor.execute(rule, body_a, body_b)
       ├─ Set cooldown timestamp
       └─ Cascade check (if any rule was cascade_eligible):
            ├─ Compare tags_before vs tags_after
            └─ If changed: _cascade_to_neighbors(body, depth + 1)
                 ├─ Prefer get_cascade_neighbors() (CascadeArea overlaps)
                 └─ Fallback: physics space query (CircleShape2D, 96px radius)
```

**Constants**: `COOLDOWN_TIME = 0.5s`, `MAX_CASCADE_DEPTH = 3`, `CASCADE_RADIUS = 96px`. Cooldowns cleaned up every 5s.

### Effect Executor

`scripts/systems/effect_executor.gd` handles 12 effect types:

| Effect | Behavior |
|--------|----------|
| DAMAGE | `take_damage(amount)` |
| DESTROY | `take_damage(99999)` |
| IGNITE | Adds HEAT_SOURCE + HOT tags, starts DOT (10 dmg/1s for 5s) |
| EXTINGUISH | Removes HEAT_SOURCE + HOT tags |
| FREEZE | Adds FROZEN + RIGID, removes LIQUID |
| MELT | Removes FROZEN + RIGID, adds LIQUID |
| CORRODE | DOT (15 dmg/1s for 3s) |
| ELECTRIFY | Instant damage (30) |
| APPLY_FORCE | Impulse away from source body |
| ADD_TAG / REMOVE_TAG | Direct tag mutation |
| TRANSFORM | Tag add + remove combo |

**DOT implementation**: Timer node added as child of target. Ticks `damage_per_tick` every `tick_interval` for `duration`. Auto-cleans when target is freed or ticks exhausted.

**Target resolution**: Effects specify `target: "a" | "b" | "both"`. Default is `"b"`.

## Physics Composition

`scenes/game_object/physics_applicator.gd` maps tags to RigidBody2D physics properties:

| Tag | Mass | Gravity | Friction | Bounce |
|-----|------|---------|----------|--------|
| HEAVY | ×3.0 | — | — | — |
| LIGHT | ×0.3 | — | — | — |
| FLOATING | — | 0.2 | — | — |
| SLIPPERY | — | — | 0.0 | — |
| STICKY | — | — | 2.0 | — |
| BOUNCY | — | — | — | 0.8 |
| Default | 1.0 | 1.0 | 0.5 | 0.0 |

Tag mutations (via `add_tag`/`remove_tag`) trigger `_reapply_physics()` to recalculate.

## Session & Persistence

### SQLite Schema (2 tables, initialized in `main.py` lifespan)

| Table | Key | Fields |
|-------|-----|--------|
| `sessions` | `id TEXT PK` | created_at, budget_used, budget_limit (default $1.00) |
| `objects` | `(session_id, object_id) PK` | blueprint_json, x, y, durability |

`blueprint_json` stores the full `GameObjectBlueprint` including `behaviors` — no schema migration required when behaviors were added.

### Session Lifecycle

1. **Create** (`POST /api/sessions`): New UUID, 15 seed objects saved via batch insert. Response includes seed blueprints, all rules, and WebSocket URL
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
| Server → Client | `pong` | — |
| Server → Client | `sprite_ready` | `object_id`, `sprite_png_base64`, `width`, `height` |
| Server → Client | `sprite_failed` | `object_id`, `reason` |
| Server → Client | `error` | `message` |

**Godot reconnect**: Exponential backoff from 1s to 30s max. On reconnect, re-requests pending sprites.
