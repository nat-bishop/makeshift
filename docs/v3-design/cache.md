# V3 Cache Design

The V3 architecture pre-computes all LLM-driven interactions at spawn time and looks them up at runtime. The cache is what makes this work — without it, every collision would need a 55ms+ LLM call.

---

## Unified cache

One cache backend with typed entries, not separate systems per cache type. Single table, single manager, one interface. Adding a new cache type = using a new type string.

### Cache types

| Type | Key | Value | Example |
|------|-----|-------|---------|
| `creation` | `"fire sword"` | All physics/affordance/destructibility/field/behavior properties | mass, height, friction, etc. |
| `pairwise` | `"fire sword::wooden shield"` | `{damage_a, damage_b, state_change, force, direction, mode}` | Collision outcome |
| `state_interaction` | `"wooden chair::on_fire"` | `{damage, state_change, mode}` | State effect on object |
| `movement_reaction` | `"zombie cop::donut"` | `{reaction, strength}` | Creature movement response |
| `destruction_result` | `"wooden shield::fire"` | `"pile of charred splinters"` + pre-generated blueprint | What remains after destruction |

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

**Pairwise + state caches — critical (performance).** Without caching, every collision needs an LLM call at runtime. The entire V3 architecture depends on pre-computing interactions at spawn time.

**Destruction results — important (latency).** Generating remains at destruction time would mean a visible delay (LLM call + image gen). Pre-caching makes destruction feel instant.

**Movement reactions — important (behavior).** Creatures need to know how to react to objects immediately, not after a 60ms delay.

---

## Edge cases

### Asymmetric pair keys

"Fire sword hits wooden shield" and "wooden shield hits fire sword" are the same collision. The cache stores damage to BOTH objects in one entry. Key is always the sorted pair so lookup order doesn't matter.

### Destruction creates new objects

"Pile of charred splinters" is a new object that needs its own creation cache entry AND pairwise interactions with everything in the scene. To avoid unbounded recursion: **depth 1 only** — remains get creation cache + pairwise interactions, but don't generate their own destruction results.

### Scene mutation during spawn integration

Player creates object A, spawn integration starts. Player creates object B before A's integration finishes. Object B's integration needs pairs with A.

Solution: creation cache is populated **synchronously** (before returning the blueprint to the client). Only pairwise/state/movement caches are populated asynchronously in the background. Object B can read A's creation cache immediately.

### Cache size growth

Pairwise cache is O(N^2) over unique object names. For 1000 unique names: ~500K entries at ~200 bytes each = ~100MB. Manageable for SQLite. Consider periodic pruning of entries not accessed in recent sessions if this grows.

### Model version coherence

If the LLM model changes (swap Qwen for Llama, update quantization), cached results may be inconsistent with fresh results. The `model_version` column enables selective invalidation:
- On model change: ignore entries with old `model_version`, or wipe the cache
- Config-driven: compare against a `CACHE_MODEL_VERSION` setting on lookup

### In-memory scene cache

Runtime lookups during collisions and field ticks must be fast. At scene load, read all relevant cache entries into an in-memory dict. Update the dict as new objects spawn and their caches populate. Keeps the hot path at O(1) dict access instead of SQLite queries.

---

## Open questions

1. **Fallback for uncached collisions** — When two objects collide before spawn integration completes, options: (a) "nothing" safe default, (b) synchronous LLM call (60ms, noticeable but not terrible). Leaning toward (a) since integration should finish well before the player can engineer collisions.

2. **Level pre-warming** — For built-in levels with known objects, should the cache be pre-populated at build time (ship a seeded `cache.db`) or computed on first load?

3. **Cloud LLM dual-path** — The 1-token call pattern is optimized for local inference (input tokens are free). Cloud APIs charge per input token, so 13 fat-prompt calls would cost more than 1 structured call. May need a dual-path if cloud support matters.
