# V3 Creation Pipeline

The exact sequence of LLM calls from player input to spawned object. All call counts assume the model and prompt formats from [llm-design-patterns.md](llm-design-patterns.md).

---

## Object creation flow

Player types a description. The backend asks questions in parallel batches:

```
"fire sword"

=== Batch 1: Properties (parallel) ===
All fired simultaneously after name resolves:
1.  Mass in kg                   → 1.5
2.  Height in cm                 → 120
3.  Surface (slick/normal/sticky)→ normal
4.  Bounce 0-100                 → 10
5.  Gravity 0-100                → 50
6.  Durability (soft→permanent)  → normal
7.  Autonomous? yes/no           → no
8.  Affordance (carry/ride/scale/none) → carry
9.  Initially burning? yes/no    → yes   ← NEW state property
10. Initially frozen? yes/no     → no
11. Initially wet? yes/no        → no
12. Initially electrified? yes/no → no
13. Catches fire? yes/no         → no
14. Can freeze? yes/no           → no
15. Gets wet? yes/no             → no
16. Conducts electricity? yes/no → no

Gated on autonomous=true:
17. Speed (crawl→rapid)          → (skipped)

=== Batch 1b: Concurrent with batch 1 ===
18. Visual description            → "flaming longsword with orange 
                                     blade and ember particles" (~20-30 tokens)
19. Destruction result name       → "splinters" (gated: durability < 6)

Total creation calls: ~19 (17 properties + visual + destruction)
Wall time: ~200ms

Note: no behavior classification at creation time. Creature behavior is
evaluated per-pair at spawn time (see below).
```

---

## Spawn integration

Runs AFTER creation, DURING sprite generation (2-5s). Player doesn't wait for this.

### Collision force rules

Two phases: a single screening call identifies pairs with interesting force interactions, then only those get evaluated. Screening is pre-warming — missed pairs are lazily evaluated on actual collision.

**Phase 1 — Screening (1 call, ~5-15 output tokens):**

```
"New object: fire sword (1.5kg, 120cm, normal, normal-surface).
 Scene objects:
 1. wooden shield (3kg, 100cm, normal, normal-surface)
 2. magnet (0.5kg, 10cm, normal, normal-surface)
 Which would have interesting force interactions (push, pull, magnetism)?
 Reply with numbers or 'none'."
 → "2"
```

**Phase 2 — Force eval (1 call per interesting pair):**

```
"fire sword (1.5kg, 120cm, normal, normal-surface) contacts
 magnet (0.5kg, 10cm, normal, normal-surface).
 none / pull / drag / push / throw"
→ "pull"
```

Result: `CollisionRule(force_on_b=-30)`. State interactions (fire spreading to wood) are NOT in the pairwise cache — they're handled by `initial_states`/`susceptible_states` + `StatePropagator`.

### Creature behavior (staged, autonomous creatures only)

For every autonomous creature in the scene, evaluate its relationship with each object in 3 sequential stages. See [architecture.md](architecture.md) for the full staged evaluation design.

```
Stage 1 + 1b (parallel, all creature×object pairs, 1 token each):
  Movement: "Zombie cop sees [fire sword]. 0=approach 1=flee 2=ignore" → 1
  Strength: "How strongly? 0-100" → 70

Stage 2 (parallel, approaching pairs only, 1 token each):
  Action: "Zombie cop is approaching [donut]. On arrival? 0=nothing 1=damage 
           2=heal 3=add state 4=remove state 5=destroy 6=take" → 5 (destroy)

Stage 3 (parallel, actions needing parameters, 1 token each):
  Params: damage amount, which state, etc.
```

If the NEW object is autonomous, run stages 1-3 for it against all existing objects.

---

## Call budget

### 7-object scene, 1 creature

| Phase | Calls | Wall time |
|---|---|---|
| Creation (new object) | ~19 | ~200ms |
| Collision screening (1 call) | 1 | ~90ms |
| Collision force eval (~2 interesting pairs × 1 call) | 2 | ~90ms |
| Creature behavior stage 1 (1 creature × 1 object, movement + priority) | 2 | ~60ms |
| Creature behavior stage 2 (~1 approaching pair) | 1 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | ~60ms |
| **Total** | **~26** | **~560ms** |

### 15-object scene, 3 creatures

| Phase | Calls | Wall time |
|---|---|---|
| Creation (new object) | ~19 | ~200ms |
| Collision screening (1 call) | 1 | ~125ms |
| Collision force eval (~4 interesting pairs × 1 call) | 4 | ~90ms |
| Creature behavior stage 1 (3 creatures × 1 object × 2 questions) | 6 | ~60ms |
| Creature behavior stage 2 (~2 approaching) | 2 | ~60ms |
| Creature behavior stage 3 (~1 needing params) | 1 | ~60ms |
| **Total (new non-creature)** | **~33** | **~595ms** |

If new object is autonomous, add: stage 1 (14 objects × 2 questions = 28 calls), stage 2 (~5), stage 3 (~3) = **~69 calls, ~770ms**.

All spawn integration runs during the 2-5s sprite gen window. Player sees no interaction latency.

---

## Scaling characteristics

Collision evaluation is O(N²) in theory, but screening reduces this significantly — most pairs have no interesting force interaction (rock+rock, sword+wood). Screening identifies ~10-15% of pairs as worth evaluating:

| Objects | Pairs | Screening calls | Interesting pairs (~10%) | Full eval calls (1 per pair) |
|---|---|---|---|---|
| 7 | 21 | 7 | ~2 | ~2 |
| 15 | 105 | 15 | ~10 | ~10 |
| 30 | 435 | 30 | ~25 | ~25 |

Screening adds 1 call per new object. Missed pairs are lazily evaluated on actual collision via `request_collision` WS message (1 call, ~100ms).

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
