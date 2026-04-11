# V3 Cache Design

The V3 architecture pre-computes all LLM-driven interactions at spawn time and looks them up at runtime. The cache is what makes this work — without it, every collision would need a 55ms+ LLM call.

---

## Unified cache

One cache backend with typed entries, not separate systems per cache type. Single table, single manager, one interface. Adding a new cache type = using a new type string.

### Cache types

| Type | Key | Value | Persistent |
|------|-----|-------|-----------|
| `creation` | `"fire sword"` | All physics/affordance/durability/state properties | Yes (cache.db) |
| `collision` | `"fire sword::wooden shield"` | `{force_on_b}` | Yes (cache.db) |
| `creature_behavior` | `"zombie cop::donut"` | `{movement, priority, action, amount, state_id}` | No (scene-local in BehaviorCache) |

`collision` entries store only force. States are handled by per-object `initial_states`/`susceptible_states` + tick-based propagation — no state outcome in the pairwise cache. Legacy `pairwise` type (6-field format) is still readable for backward compatibility.

All types have the same access pattern: composite key, JSON value, check before compute, write once.

### Interface

```python
await cache.get("creation", "fire sword")
await cache.set("creation", "fire sword", properties_dict)
await cache.exists("pairwise", "fire sword::wooden shield")
```

### Storage

```sql
CREATE TABLE cache (
    cache_type TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (cache_type, cache_key)
);
```

---

## Separate database

Two SQLite files with different purposes:

| File | Contents | Access pattern | Lifetime |
|------|----------|----------------|----------|
| `game.db` | Sessions, per-session objects (position, durability) | Mutable, per-player, transactional | Ephemeral — reset during dev |
| `cache.db` | All LLM result caches | Append-only, global, immutable after write | Persistent — survives session wipes |

Benefits:
- `rm game.db` resets game state without re-running all LLM calls
- Cache can be shared/copied between installations
- Different access patterns don't contend (cache reads during gameplay vs session writes)

Both use aiosqlite (already a dependency).

---

## Key normalization

All cache keys are normalized the same way:
- Lowercase
- Strip whitespace
- Collapse internal whitespace to single space
- For pair keys: sort lexicographically, join with `::`

`"Fire Sword"` and `"fire sword"` and `" FIRE  SWORD "` all map to `"fire sword"`.

`("wooden shield", "fire sword")` and `("fire sword", "wooden shield")` both map to `"fire sword::wooden shield"`.

---

## Keyed by name, not ID

Cache keys use **object names**, not UUIDs. This is both a correctness requirement ("two identical objects should have identical physics") and an efficiency win — the cache amortizes across all sessions. A "fire sword" created by player A benefits player B.

---

## Cache importance by type

**Creation cache — critical (correctness).** Without it, two "fire swords" get different physics. Players can't predict what they're creating.

**Collision cache — important (latency).** Without caching, every collision cache miss triggers a WS round-trip for lazy eval. Pre-warming at spawn means the common case is a dict lookup. Stores only `force_on_b` — state interactions are now handled by `initial_states`/`susceptible_states` per object.

**Creature behavior — scene-local only, not in persistent cache.db.** Creature behavior prompts include scene context ("Scene: [burning tree, bucket of water, ...]"), so results are scene-dependent — a firefighter reacts differently to water when fire exists. The cache key `"firefighter::bucket of water"` can't capture this. Creature behavior is stored in-memory per scene, computed at spawn time, and re-evaluated when an object's states change. Cheap enough to recompute — no persistence needed.

**Destruction results — important (latency).** Generating remains at destruction time would mean a visible delay (LLM call + image gen). Pre-caching makes destruction feel instant.

---

## Edge cases

### Sorted-key convention

Pair keys are lexicographically sorted: `"fire sword::wooden shield"`. At runtime, collision participants arrive in arbitrary order. `CollisionRule.force_on_b` always refers to the **second name in lexicographic sort order**. The engine maps collision participants to cache A/B by sorting their names.

"Fire sword hits wooden shield" and "wooden shield hits fire sword" are the same collision. Key is always the sorted pair so lookup order doesn't matter.

### Destruction creates new objects

"Pile of charred splinters" is a new object that needs its own creation cache entry AND pairwise interactions with everything in the scene. To avoid unbounded recursion: **depth 1 only** — remains get creation cache + pairwise interactions, but don't generate their own destruction results.

### Scene mutation during spawn integration

Player creates object A, spawn integration starts. Player creates object B before A's integration finishes. Object B's integration needs pairs with A.

Solution: creation cache is populated **synchronously** (before returning the blueprint to the client). Only pairwise and creature behavior caches are populated asynchronously in the background. Object B can read A's creation cache immediately.

### Cache size growth

Pairwise cache is O(N^2) over unique object names. For 1000 unique names: ~500K entries at ~200 bytes each = ~100MB. Manageable for SQLite. Consider periodic pruning of entries not accessed in recent sessions if this grows.

### Model version coherence

If the LLM model changes (swap Qwen for Llama, update quantization), cached results may be inconsistent with fresh results. The `model_version` column enables selective invalidation:
- On model change: ignore entries with old `model_version`, or wipe the cache
- Config-driven: compare against a `CACHE_MODEL_VERSION` setting on lookup

### In-memory scene cache

Runtime lookups during collisions and field ticks must be fast. At scene load, read all relevant cache entries into an in-memory dict. Update the dict as new objects spawn and their caches populate. Keeps the hot path at O(1) dict access instead of SQLite queries.

---

## Collision rules vs. creature behaviors on state change

**Collision rules are permanent** — `state_changed` does NOT re-evaluate `CollisionRule` entries. Force between two objects is a property of their materials and shapes, not their runtime state.

**Creature behaviors are re-evaluated** — when an object's active states change, all creature behaviors toward that object are invalidated and re-evaluated with the new state context. A firefighter's reaction to a burning tree differs from its reaction after the fire is extinguished. Re-eval is triggered by `state_changed` WS message from client → `_handle_state_changed()` in `ws/handler.py`.

---

## Design decisions

**Uncached collision fallback:** lazy eval via `request_collision` WS message. Client hits cache miss → sends `request_collision(name_a, name_b)` → server evaluates and pushes `collision_ready`. Deduped via `_pending_evals` on client. Force-only eval is 1 LLM call (~100ms), not the old 6-call round-trip.

**Level pre-warming:** Ship a seeded `cache.db` for release builds (eliminates first-load latency). Compute on first load for dev to test the pipeline.

**Cloud LLM dual-path:** Not a cache concern — the cache stores results regardless of how they were computed. The 1-token call pattern is optimized for local inference (input tokens are free). Cloud APIs charge per input token, so a dual-path with structured output may be needed. See [architecture.md](architecture.md) for inference strategy.
