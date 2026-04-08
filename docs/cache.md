# Cache Design

The V3 architecture pre-computes all LLM-driven interactions at spawn time and looks them up at runtime. The cache is what makes this work — without it, every collision would need a 55ms+ LLM call.

---

## Unified cache

One cache backend with typed entries, not separate systems per cache type. Single table, single manager, one interface. Adding a new cache type = using a new type string.

### Cache types

| Type | Key | Value | Example |
|------|-----|-------|---------|
| `creation` | `"fire sword"` | All physics/affordance/destructibility/field properties | mass, height, friction, etc. |
| `pairwise` | `"fire sword::wooden shield"` | `{damage_a, damage_b, state_change_a, state_change_b, force_b, direction_b, destroy_a, destroy_b, mode}` | Collision outcome (9 fields) |
| `creature_behavior` | `"zombie cop::donut"` | `{reaction, strength, action, param}` | Full creature×object behavior (scene-local, not persistent — see below) |
| `destruction_result` | `"wooden shield"` | `"broken wooden shield"` + pre-generated blueprint | What remains after destruction |

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

**Pairwise cache — critical (performance).** Without caching, every collision needs an LLM call at runtime. The entire V3 architecture depends on pre-computing interactions at spawn time.

**Creature behavior — scene-local only, not in persistent cache.db.** Creature behavior prompts include scene context ("Scene: [burning tree, bucket of water, ...]"), so results are scene-dependent — a firefighter reacts differently to water when fire exists. The cache key `"firefighter::bucket of water"` can't capture this. Creature behavior is stored in-memory per scene, computed at spawn time (~180ms for 3 creatures × 14 objects), and re-evaluated on scene changes. Cheap enough to recompute — no persistence needed.

**Destruction results — important (latency).** Generating remains at destruction time would mean a visible delay (LLM call + image gen). Pre-caching makes destruction feel instant.

---

## Edge cases

### Sorted-key convention

Pair keys are lexicographically sorted: `"fire sword::wooden shield"`. At runtime, collision participants arrive in arbitrary order. Convention: `damage_a`, `state_change_a`, `destroy_a` always refer to the **first name in lexicographic sort order**. The engine maps collision participants to cache A/B by sorting their names.

"Fire sword hits wooden shield" and "wooden shield hits fire sword" are the same collision. The cache stores effects on BOTH objects in one entry. Key is always the sorted pair so lookup order doesn't matter.

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

## Pairwise cache re-evaluation on state change

When an object gains or loses a state, its pairwise cache entries are stale. Strategy: **always re-evaluate on state change.** The base entry is overwritten. When the state is later removed, re-evaluate again to restore base behavior.

This is cheap because re-evaluation is **lazy** — only triggered on next collision or field tick. Most stale pairs never get re-evaluated because the objects aren't near each other. Cost per actual re-evaluation: 9 parallel 1-token calls (~145ms).

Re-evaluation prompts include active states in the object description:
```
"[fire sword: 2kg, armor 80, hp 90, field 150cm] collides with
 [wooden shield [ON_FIRE]: 3kg, armor 20, hp 40, no field]."
```

Same 9-call format, same parallelism.

---

## Design decisions

**Uncached collision fallback:** "nothing" safe default. Spawn integration runs during sprite gen (2-5s). Players can't engineer collisions with a half-spawned object that fast. If they do, "nothing" is harmless — the interaction works normally once the cache populates.

**Level pre-warming:** Ship a seeded `cache.db` for release builds (eliminates first-load latency). Compute on first load for dev to test the pipeline.

**Cloud LLM dual-path:** Not a cache concern — the cache stores results regardless of how they were computed. The 1-token call pattern is optimized for local inference (input tokens are free). Cloud APIs charge per input token, so a dual-path with structured output may be needed. See [architecture.md](architecture.md) for inference strategy.
