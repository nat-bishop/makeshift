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

# Evals — NOT in `make test`:
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
- `routers/` — `objects.py` (POST create), `sessions.py` (CRUD + sync), `interactions.py`

**Godot Client** (`godot/`): Godot 4.6.2 .NET/Mono build, C#, .NET 8.

- Editor version string must read `.mono.official` — the standard build has no `.cs` resource loader and fails with "No loader found for resource" on every autoload.
- `Godot.NET.Sdk` in `godot/makeshift.csproj` must match the editor's minor version (currently `4.6.2`).
- `make play` / `make dev` run `cd godot && dotnet build` before launching Godot.

- Autoloads in `autoloads/`: `EventBus`, `InteractionCache`, `Backend`, `GameManager`, `Logger`, `PrespawnCatalog` — all with `public static T Instance { get; private set; } = null!;` pattern. Note: `Logger` is registered as `Log=` in `project.godot`, but call sites use `Logger.Instance` (the class's static field).
- Key systems in `scripts/systems/`: `ObjectBehavior.cs`, `StateManager.cs`, `StatePropagator.cs`, `AffordanceSystem.cs`, `PhysicsComposer.cs`, `WorldMutations.cs`
- Data in `scripts/data/`: `Enums.cs` (canonical enums — integer values are wire-format; don't reorder without backend changes), `StateContradictions.cs`, `CollisionLayers.cs`
- Models in `scripts/models/`: C# records — `Blueprint`, `BehaviorEntry`, `PhysicsData`, `VisualDescriptor`, `WsMessage` hierarchy; `MakeshiftJsonContext` (source-gen JSON, snake_case)
- Interfaces in `scripts/interfaces/`: typed contracts that replace GDScript duck typing (`IDamageable`, `IStateful`, `IWorld`, etc.)

## Gotchas

- `ObjectBehavior` runs in `_PhysicsProcess()` (~60fps), NOT tick-based. First action fires immediately at CONTACT_RANGE (48 units), then ACTION_COOLDOWN (1.0s). Critical for reactive objects like bombs.
- Background `asyncio.Task`s must be held in a module-level `set` to prevent GC before completion (see `routers/objects.py`, `ws/handler.py`)
- `@computed_field` properties require `# type: ignore[prop-decorator]` — mypy doesn't support decorators above `@property`
- `Timer` type ambiguity in C#: .NET 8 implicit usings pull in `System.Threading.Timer`. Must alias: `using Timer = Godot.Timer;` — affects `WorldMutations`, `StateDecay`, `StatePropagator`. Same pattern for `HttpClient` and `FileAccess` in `Backend.cs`.
- `Logger` name collision in Godot 4.6+: `Godot.Logger` now exists and collides with `Makeshift.Autoloads.Logger`. Any file with `using Makeshift.Autoloads;` + `using Godot;` must also have `using Logger = Makeshift.Autoloads.Logger;`.
- Async continuations in `Backend.cs` run on threadpool (no Godot `SynchronizationContext`) — use `CallDeferred` for anything touching Godot nodes from a `Task` continuation.
- `Godot.Collections.Array`/`Dictionary` required for signal parameters with collections — C# generic types cross the marshaling boundary and silently fail or error.
- `partial class` required on every Godot-derived class — source generators need it.
- `Backend` autoload has `process_mode = PROCESS_MODE_ALWAYS` — must process during pause for WS keepalive.
- Collision layer bitmask vs UI index — `CollisionLayer`/`CollisionMask` are bitmasks, not UI layer numbers. UI Layer 1 = bit 1, Layer 2 = bit 2, Layer 3 = bit 4 (powers of 2).
- `pytest-asyncio` configured with `asyncio_mode = "auto"` — `async def` tests run without extra markers.
- `make check` enforces `ruff format --check` before lint/typecheck/test — run `make format` to fix.

## Documentation

See [docs/index.md](docs/index.md) for the full knowledge base — architecture, engine primitives, creation pipeline, caching, LLM design patterns, level design, research references.
