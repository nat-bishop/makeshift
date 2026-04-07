# V3 Creation Pipeline

The exact sequence of LLM calls from player input to spawned object. All call counts assume the model and prompt formats from [llm-design-patterns.md](llm-design-patterns.md).

---

## Object creation flow

Player types a description. The backend asks questions in parallel batches:

```
"fire sword"

=== Batch 1: Properties (parallel, ~60ms) ===
All 1-token outputs, fired simultaneously:
1. Mass in kg                    → 2
2. Height in meters              → 1.2
3. Friction 0-100                → 30
4. Bounce 0-100                  → 10
5. Gravity 0-100                 → 50
6. Armor 0-100                   → 80
7. HP 0-100                      → 90
8. Indestructible? 0/1           → 1 (yes, destructible)
9. Has field? 0/1                → 1
10. Field range in meters        → 1.5
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

For every existing object in the scene, evaluate the pair:

```
Per pair, 5 parallel calls (1 token each, ~60ms):
"[fire sword: 2kg, armor 80, hp 90, emits heat] hits 
 [wooden shield: 3kg, armor 20, hp 40]. Damage to A? 0-100"     → 0
"Same. Damage to B? 0-100"                                       → 40
"Same. State change to B? 0-12 (0=none 1=on_fire 2=frozen...)"  → 1
"Same. Force on B? 0-100 (0=none). Direction? 0=push 1=pull"    → 20, 0
"Same. 0=instant 1=continuous"                                    → 1
```

Include physics properties in the prompt. Input is free — stuff as much calibration context as needed.

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
| Passive pairwise (6 pairs × 5 calls) | 30 | 30 | ~240ms |
| Creature behavior stage 1+1b (1 creature × 1 object × 2) | 2 | 2 | ~60ms |
| Creature behavior stage 2 (~1 approaching pair) | 1 | 1 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | 1 | ~60ms |
| **Total** | **47** | **~74** | **~620ms** |

### 15-object scene, 3 creatures

| Phase | Calls | Tokens | Wall time |
|---|---|---|---|
| Creation (new object) | 13 | ~40 | ~200ms |
| Passive pairwise (14 pairs × 5 calls) | 70 | 70 | ~540ms |
| Creature behavior stage 1+1b (3 creatures × 1 object × 2) | 6 | 6 | ~60ms |
| Creature behavior stage 2 (~2 approaching) | 2 | 2 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | 1 | ~60ms |
| **Total (new non-creature)** | **92** | **~119** | **~920ms** |

If new object is autonomous, add: stage 1+1b (14 objects × 2 = 28), stage 2 (~5), stage 3 (~3) = **~128 calls, ~1,100ms**.

All spawn integration runs during the 2-5s sprite gen window. Player sees no interaction latency.

### Full scene initialization (15 objects from scratch)

| Phase | Calls | Tokens |
|---|---|---|
| Creation (15 objects × 13) | 195 | ~600 |
| Passive pairwise (105 pairs × 5) | 525 | 525 |
| Creature behavior stage 1+1b (3 creatures × 14 objects × 2) | 84 | 84 |
| Creature behavior stage 2 (~12 approaching pairs) | 12 | 12 |
| Creature behavior stage 3 (~8 needing params) | 8 | 8 |
| **Total** | **824** | **~1,229** |

At 8 parallel, 60ms per batch: ~103 batches × 60ms = **~6.2 seconds**. This is scene load time, not per-object. Runs once when the level starts.

---

## Scaling characteristics

Pairwise evaluation is O(N²). This is the fundamental constraint on scene size:

| Objects | Pairs | Pairwise calls (5 per pair) |
|---|---|---|
| 7 | 21 | 105 |
| 15 | 105 | 525 |
| 30 | 435 | 2,175 |

Scribblenauts on DS managed 10-15 simultaneous objects. Reasonable starting target.

---

## Pre-caching strategy

1. **Creation cache:** Same object name → same physics from cache. "Fire sword" always gets mass 2.0 after first creation.
2. **Sprite cache:** Keyed by SHA-256 of description. Identical descriptions share sprites across sessions.

---

## Open questions

**Interaction call format.** The 5-call-per-pair format (damage A, damage B, state, force, mode) needs prompt testing with the actual LLM. May need to split differently or combine some fields.

**Balance.** All numbers from the LLM. Calibration examples set the scale. No global balance constraint. May need post-hoc validation: flag results where damage > HP (one-shot kills) for review.

**State change re-evaluation.** When an object gains a state, its pairwise cache entries are stale. Lazy invalidation (re-evaluate on next contact/field tick) means a brief window where stale data could be used. In practice, the state change and the next interaction are usually triggered by the same event (fire sword hits wall → wall gains on_fire → field tick re-evaluates nearby pairs).

---

## Implementation notes

### Orchestration pattern

Use `asyncio.gather()` with a data-driven question list. Preferred over `asyncio.TaskGroup` because:
- All calls are independent (no inter-task dependencies)
- If one fails, retry it individually rather than canceling siblings
- `gather(return_exceptions=True)` gives per-call error handling

The question list pattern (see [architecture.md](architecture.md)) makes the pipeline editable during playtesting — add/remove/tweak properties by editing a data list, not orchestration code.
