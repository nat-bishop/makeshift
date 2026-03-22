# Architecture

## System Overview

```
Godot 4 Client                          FastAPI Backend
┌──────────────────┐                   ┌──────────────────────────┐
│ ObjectCreationPanel                  │                          │
│   └─ Backend.create_object() ──POST──►  /api/sessions/{id}/objects │
│                                      │    └─ PydanticAI agent ─────► Gemini LLM
│ Backend (autoload)                   │    └─ placeholder PNG ◄──┘  │
│   ├─ HTTP client ◄─── JSON ─────────┤                          │
│   └─ WebSocket  ◄── sprite_ready ───┤  Background task ────────────► Flux (fal.ai)
│                                      │    └─ rembg / birefnet  │
│ RuleEngine (autoload)                │                          │
│   └─ mirrors backend rules           │  aiosqlite               │
│                                      │    └─ sessions, objects, │
│ CollisionResolver (autoload)         │       inventory, equipment│
│   └─ EffectExecutor                  │                          │
└──────────────────┘                   └──────────────────────────┘
```

## Object Creation Pipeline

Full flow from player input to world-placed object with sprite:

1. **Player types description** → `ObjectCreationPanel` sends text to `Backend.create_object()`
2. **HTTP POST** → `POST /api/sessions/{id}/objects` with `{"description": "..."}`
3. **Budget check** → `SessionManager.get_budget_info()` verifies remaining budget (rejects with 402 if exhausted)
4. **LLM agent** → `creator.agent.create_object()` runs PydanticAI agent (Gemini 3.1 Flash Lite Preview, 3 retries). Validators enforce: 1-3 word name, 2-6 tags, no contradictions, budget ≤ 10. Falls back to generic "Mysterious {description}" on failure
5. **Blueprint construction** → `GameObjectBlueprint` adds UUID, computed fields: `power_cost`, `is_equippable`, `equip_slot`, `equip_tags`, `starting_durability`
6. **Atomic persist** → `track_cost_and_save_object()` charges $0.041 + saves blueprint in one commit
7. **Immediate response** → Client receives blueprint JSON + placeholder PNG (colored rounded rectangle) + budget_remaining
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

`RuleResolver` builds a two-tier index at init from ~55 `InteractionRule` definitions:

**Pair index** (O(1) lookup): Nested dict `tag_a → tag_b → [rules]`. For bidirectional rules, both `(a,b)` and `(b,a)` entries are created.

**Wildcard rules** (O(n) scan, n ≈ 3-5): Rules where `tags_required_b` is empty. Match when `tags_required_a ⊆ tags_a` (or `⊆ tags_b` if bidirectional).

**Matching algorithm** (`find_matching_rules`):
1. For each tag pair `(ta, tb)` where `ta ∈ tags_a` and `tb ∈ tags_b`: check pair index, verify full tag subset inclusion
2. Scan wildcard rules for subset matches
3. Deduplicate by `rule_id`, sort by priority descending

### Godot: `autoloads/rule_engine.gd`

Mirrors the backend resolver. Rules are loaded from session response JSON (`Backend.create_session()` or `Backend.restore_session()`). Same two-tier index, same matching logic. Exists so collision resolution doesn't require a server round-trip.

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

`scripts/systems/effect_executor.gd` handles 14 effect types:

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
| TRANSFORM / CHANGE_PROPERTY | Tag add + remove combo |
| SPAWN | Stub — logs warning |

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

### SQLite Schema (4 tables, initialized in `main.py` lifespan)

| Table | Key | Fields |
|-------|-----|--------|
| `sessions` | `id TEXT PK` | created_at, budget_used, budget_limit (default $1.00), current_level, levels_completed (JSON) |
| `objects` | `(session_id, object_id) PK` | blueprint_json, x, y, durability |
| `inventory` | `(session_id, slot) PK` | object_id (nullable) |
| `equipment` | `session_id PK` | equipment_json |

### Session Lifecycle

1. **Create** (`POST /api/sessions`): New UUID, 8 empty inventory slots, empty equipment, 15 seed objects saved via batch insert. Response includes seed blueprints, all rules, and WebSocket URL
2. **Restore** (`GET /api/sessions/{id}`): Full load — session row + objects + inventory + equipment
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
