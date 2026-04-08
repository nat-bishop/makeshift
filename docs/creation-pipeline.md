# Creation Pipeline

The exact sequence of LLM calls from player input to spawned object. All call counts assume the model and prompt formats from [llm-design-patterns.md](llm-design-patterns.md).

---

## Object creation flow

Player types a description. The backend asks questions in parallel batches:

```
"fire sword"

=== Batch 1: Properties (parallel, ~60ms) ===
Most are 1-token integer outputs. Mass is the exception (real-world kg, may be 2-4 tokens for decimals — grounding in real units matters for answer quality). All fired simultaneously:
1. Mass in kg                    → 1.5  (real-world unit, decimal OK)
2. Height in cm                  → 120  (integer, real-world grounded)
3. Friction 0-100                → 30
4. Bounce 0-100                  → 10
5. Gravity 0-100                 → 50
6. Armor 0-100                   → 80
7. HP 0-100                      → 90
8. Indestructible? 0/1           → 1 (yes, destructible)
9. Has field? 0/1                → 1
10. Field range in cm            → 150  (integer, real-world grounded)
11. Autonomous? 0/1              → 0

=== Batch 1b: Concurrent with batch 1 (~200ms) ===
These take more output tokens but run simultaneously:
12. Visual description            → "flaming longsword with orange 
                                     blade and ember particles" (~20-30 tokens)
13. Affordance 0-3               → 0 (carry)

Total creation calls: 13
Total output tokens: ~15 for properties + ~25 for visual = ~40
Wall time: ~200ms (batches 1+1b in parallel)

Note: no behavior classification at creation time. Creature behavior is
evaluated per-pair at spawn time (see below).
```

---

## Spawn integration

Runs AFTER creation, DURING sprite generation (2-5s). Player doesn't wait for this.

### Passive pairwise interactions

Two phases: a single screening call identifies interesting pairs, then only those get fully evaluated.

**Phase 1 — Screening (1 call, ~5-15 output tokens, ~100-160ms):**

```
"New object: fire sword (2kg, armor 80, hp 90, hot, sharp, metal).
 Scene objects:
 1. wooden shield (3kg, armor 20, hp 40, flammable, wood)
 2. rock (5kg, armor 70, hp 80, stone)
 3. glass bottle (0.3kg, armor 5, hp 10, fragile, glass)
 4. rope (0.5kg, armor 10, hp 20, fiber)
 5. campfire (hot, fire, field)
 Which would interact interestingly with fire sword? List numbers."
 → "1,3"
```

The LLM sees all objects at once and makes relative judgments — fire sword + campfire is redundant (both hot), fire sword + rock is boring (nothing happens), but fire sword + wooden shield and fire sword + glass bottle are interesting. A missed pair defaults to "nothing happens" — low stakes since pairs can be lazily evaluated on actual contact.

**Phase 2 — Full eval (K interesting pairs × 9 parallel calls, ~145ms per batch):**

Only pairs from the screening list get evaluated. 9 calls per pair, all 1 token, all parallel:

```
Context prefix (shared across all 9 calls, input is free):
"[fire sword: 2kg, armor 80, hp 90, emits heat] collides with
 [wooden shield: 3kg, armor 20, hp 40]."

1. "Damage to fire sword? 0-100"                  → 0
2. "Damage to wooden shield? 0-100"                → 40
3. "State change on fire sword? 0-14"              → 0   (none)
4. "State change on wooden shield? 0-14"           → 1   (add on_fire)
5. "Force on wooden shield? 0-100"                 → 20
6. "Push or pull? 0=push 1=pull"                   → 0
7. "Fire sword destroyed? 0=no 1=yes"              → 0
8. "Wooden shield destroyed? 0=no 1=yes"           → 0
9. "Instant or continuous? 0=instant 1=continuous"  → 0
```

State encoding 0-14: `0`=none, `1-7`=add state (on_fire, frozen, wet, electrified, poisoned, corroded, molten), `8-14`=remove same states. Covers both add and remove — needed because `electrified`, `poisoned`, `corroded` have no contradictions and can only be removed explicitly.

A and B refer to the first and second name in lexicographic sort order. See [cache.md](cache.md) for key convention.

Force on A is engine-derived (Newton's 3rd law heuristic), not LLM-evaluated. See [engine-primitives.md](engine-primitives.md) for the full mapping.

### Creature behavior (staged, autonomous creatures only)

For every autonomous creature in the scene, evaluate its relationship with each object in 3 sequential stages. See [architecture.md](architecture.md) for the full staged evaluation design.

```
Stage 1 + 1b (parallel, all creature×object pairs, 1 token each):
  Movement: "Zombie cop sees [fire sword]. 0=approach 1=flee 2=orbit 3=ignore" → 1
  Strength: "How strongly? 0-100" → 70

Stage 2 (parallel, approaching/orbiting pairs only, 1 token each):
  Action: "Zombie cop is approaching [donut]. On arrival? 0=nothing 1=damage 
           2=heal 3=add state 4=remove state 5=destroy 6=take" → 5 (destroy)

Stage 3 (parallel, actions needing parameters, 1 token each):
  Params: damage amount, which state, etc.
```

If the NEW object is autonomous, run stages 1-3 for it against all existing objects.

---

## Call budget

### 7-object scene, 1 creature

| Phase | Calls | Tokens | Wall time |
|---|---|---|---|
| Creation (new object) | 13 | ~40 | ~200ms |
| Pairwise screening (1 call) | 1 | ~5 | ~90ms |
| Pairwise full eval (~2 interesting pairs × 9 calls) | 18 | 18 | ~145ms |
| Creature behavior stage 1+1b (1 creature × 1 object × 2) | 2 | 2 | ~60ms |
| Creature behavior stage 2 (~1 approaching pair) | 1 | 1 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | 1 | ~60ms |
| **Total** | **36** | **~67** | **~615ms** |

### 15-object scene, 3 creatures

| Phase | Calls | Tokens | Wall time |
|---|---|---|---|
| Creation (new object) | 13 | ~40 | ~200ms |
| Pairwise screening (1 call) | 1 | ~10 | ~125ms |
| Pairwise full eval (~4 interesting pairs × 9 calls) | 36 | 36 | ~145ms |
| Creature behavior stage 1+1b (3 creatures × 1 object × 2) | 6 | 6 | ~60ms |
| Creature behavior stage 2 (~2 approaching) | 2 | 2 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | 1 | ~60ms |
| **Total (new non-creature)** | **59** | **~95** | **~650ms** |

If new object is autonomous, add: stage 1+1b (14 objects × 2 = 28), stage 2 (~5), stage 3 (~3) = **~95 calls, ~830ms**.

All spawn integration runs during the 2-5s sprite gen window. Player sees no interaction latency.

### Full scene initialization (15 objects from scratch)

| Phase | Calls | Tokens |
|---|---|---|
| Creation (15 objects × 13) | 195 | ~600 |
| Pairwise screening (15 calls, 1 per object as it enters) | 15 | ~100 |
| Pairwise full eval (~25 interesting pairs × 9) | 225 | 225 |
| Creature behavior stage 1+1b (3 creatures × 14 objects × 2) | 84 | 84 |
| Creature behavior stage 2 (~12 approaching pairs) | 12 | 12 |
| Creature behavior stage 3 (~8 needing params) | 8 | 8 |
| **Total** | **539** | **~1,029** |

Fire all calls via `asyncio.gather()` — SGLang's continuous batching handles scheduling. At effective concurrency of ~32, 60ms per batch: ~17 batches × 65ms = **~1.1 seconds**. This is scene load time, not per-object. Runs once when the level starts.

---

## Scaling characteristics

Pairwise evaluation is O(N²) in theory, but screened pairwise reduces this significantly — most pairs are uninteresting (rock+rock, sword+sword). The screening call identifies ~25% of pairs as worth evaluating:

| Objects | Pairs | Screening calls | Interesting pairs (~25%) | Full eval calls (9 per pair) |
|---|---|---|---|---|
| 7 | 21 | 7 | ~5 | ~45 |
| 15 | 105 | 15 | ~25 | ~225 |
| 30 | 435 | 30 | ~60 | ~540 |

Screening adds 1 call per new object (~100-160ms). Missed pairs default to "nothing happens" and can be lazily evaluated on actual contact.

Scribblenauts on DS managed 10-15 simultaneous objects. Reasonable starting target.

---

## Pre-caching strategy

1. **Creation cache:** Same object name → same physics from cache. "Fire sword" always gets mass 2.0 after first creation.
2. **Sprite cache:** Keyed by SHA-256 of description. Identical descriptions share sprites across sessions.

---

## Open questions

**Balance.** All numbers from the LLM. Calibration examples set the scale. No global balance constraint. May need post-hoc validation: flag results where damage > HP (one-shot kills) for review.

---

## Implementation notes

### Orchestration pattern

Use `asyncio.gather()` with a data-driven question list. Preferred over `asyncio.TaskGroup` because:
- All calls are independent (no inter-task dependencies)
- If one fails, retry it individually rather than canceling siblings
- `gather(return_exceptions=True)` gives per-call error handling

Fire all requests concurrently — don't manually batch. SGLang's continuous batching handles scheduling internally, batching prefill and decode phases independently. Effective concurrency is ~32 calls before GPU degradation (benchmarked). If overloaded, SGLang returns 503 — handle with retry (PydanticAI has built-in retry).

The question list pattern (see [architecture.md](architecture.md)) makes the pipeline editable during playtesting — add/remove/tweak properties by editing a data list, not orchestration code.
