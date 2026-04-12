# CLAUDE.md

## Project Overview

Makeshift — "Scribblenauts meets Terraria." A 2D sandbox where players type descriptions to create game objects via LLM (Gemini), with sprites generated locally by FLUX (text-to-image + img2img). A Python/FastAPI backend serves a Godot 4 client.

## Commands

```bash
make dev                       # start all servers + launch game
make api                       # start FastAPI dev server (foreground, Ctrl-C to restart)
make gpu                       # start Docker GPU containers (detached, run once)
make stop                      # stop everything
make check                     # format check + lint + typecheck + test
make test                      # run tests only
make format                    # format code (run before check)

# Evals cost money — NOT in `make test`:
make eval                      # all quality gate evals
make eval-creation             # creation pipeline quality
make eval-behavior             # behavior + screening quality

# Run `make help` for full command list, `make cli-status` to check services
```

## Architecture

**Backend** (`backend/app/`): FastAPI, async everywhere (aiosqlite, httpx).

- `creator/` — Object creation pipeline. `pipeline.py` orchestrates parallel LLM calls → `GameObjectBlueprint`
- `engine/behavior.py` — Unified behavior system. Screening → staged eval → `BehaviorEntry`
- `models/` — `blueprint.py` (`GameObjectBlueprint`, `PLAYER_BLUEPRINT`), `state.py` (4 states), `session.py`
- `images/` — Sprite generation. `local_image.py` (FLUX text-to-image + img2img edits) + `birefnet_bg.py` (bg removal) + `pipeline.py` (orchestration, img2img use-case functions)
- `cache/` — `scene.py` (`BehaviorCache`, scene-local), `store.py` (creation cache, persistent in `cache.db`)
- `ws/handler.py` — WebSocket: `sprite_ready`, `combined_sprite_ready`, `destruction_sprite_ready`, `behaviors_ready`, `behavior_updated`
- `sessions/manager.py` — aiosqlite (`game.db`). Budget: $1.00/session at $0.041/object
- `routers/` — `objects.py` (POST create), `sessions.py` (CRUD + sync)

**Godot Client** (`godot/`): Godot 4.6, GDScript.

- Autoloads: `EventBus` (signals), `InteractionCache` (behavior lookup), `Backend` (HTTP+WS), `GameManager` (state), `Log`
- Key systems in `scripts/systems/`: `object_behavior.gd`, `state_manager.gd`, `state_propagator.gd`, `affordance_system.gd`, `physics_composer.gd`, `world_mutations.gd`
- Data in `scripts/data/`: `state_contradictions.gd` (canonical `STATE_NAMES`), `collision_layers.gd`

## Gotchas

- `ObjectBehavior` runs in `_physics_process()` (~60fps), NOT tick-based. First action fires immediately at CONTACT_RANGE (48 units), then ACTION_COOLDOWN (1.0s). Critical for reactive objects like bombs.
- Background `asyncio.Task`s must be held in a module-level `set` to prevent GC before completion (see `routers/objects.py`, `ws/handler.py`)
- `@computed_field` properties require `# type: ignore[prop-decorator]` — mypy doesn't support decorators above `@property`
- GDScript `:=` type inference fails on Variant-returning functions — `abs()`, `clamp()`, `min()`, `max()`, array/dict element access, `instantiate()`. Use explicit type or untyped, never `:=`.
- `@onready` vars are null before `add_child()` — if a setup method runs before the node enters the tree, `@onready` references are null. Store params in plain vars, apply in `_ready()`.
- Collision layer bitmask vs UI index — `collision_layer`/`collision_mask` are bitmasks, not UI layer numbers. UI Layer 1 = bit 1, Layer 2 = bit 2, Layer 3 = bit 4 (powers of 2).
- In Godot 4.x, assigning an untyped `Array` (e.g. from JSON parsing) to a typed `Array[Dictionary]` silently fails. Use untyped `Array` or iterate-and-append.
- `Backend` autoload has `process_mode = PROCESS_MODE_ALWAYS` — must process during pause for WS keepalive.
- `pytest-asyncio` configured with `asyncio_mode = "auto"` — `async def` tests run without extra markers.
- `make check` enforces `ruff format --check` before lint/typecheck/test — run `make format` to fix.

## Documentation

See [docs/index.md](docs/index.md) for the full knowledge base — architecture, engine primitives, creation pipeline, caching, LLM design patterns, level design, research references.
