# Creation Pipeline

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
18. Visual description            → "Cut paper flames in orange and red
                                     over a cardboard blade, foil hilt" (~60-80 tokens)
19. Destruction result name       → "splinters" (gated: durability < 6)

Total creation calls: ~19 (17 properties + visual + destruction)
Wall time: ~200ms

Note: no behavior classification at creation time. Creature behavior is
evaluated per-pair at spawn time (see below).
```

---

## Spawn integration

Runs AFTER creation, DURING sprite generation (2-5s). Player doesn't wait for this.

### img2img sprite pre-generation

After the base sprite arrives (`sprite_ready`), two img2img tasks fan out in parallel using the base sprite bytes:

- **Destruction sprite** (if `durability < 6`): FLUX img2img transforms the object sprite into a visually distinct debris pile. Delivered via `destruction_sprite_ready` WS message; cached on the debris blueprint as `_preloaded_sprite` meta in Godot.
- **Carry/ride sprite** (if `affordance == carry or ride`): FLUX img2img composites the player sprite + object sprite into a carrying/riding scene. Delivered via `combined_sprite_ready`.

Both use LLM-generated descriptions (`ask_text`, ≤250 tokens) wrapped in a shared art style template. See [image-combination.md](image-combination.md) for pipeline details and prompt design.

### Behavior evaluation

Bidirectional screening (1 call per spawn) identifies pairs with interesting interactions. Then staged evaluation per pair.

**Phase 1 — Screening (1 call, ~5-15 output tokens):**

```
"New object: fire sword (1.5kg, 120cm, normal-surface).
 Scene objects:
 1. wooden shield (3kg, 100cm, normal-surface)
 2. zombie (70kg, 170cm, normal-surface)
 Which would have interesting interactions with fire sword?
 Reply with numbers or 'none'."
 → "2"
```

**Phase 2 — Staged behavior eval (per interesting pair):**

Stage 1: movement (approach/flee/ignore) + priority (0-3) — parallel, 2 calls.
Stage 2: composite action (nothing/damage/heal/consume/push) + amount + state modifier + force modifier — parallel, up to 4 calls.

See [architecture.md](architecture.md) for the full staged evaluation design.

### Object behavior (staged, all interesting pairs)

For every scene object that passes screening, evaluate both directions with the new object. The player is always included as a potential target via `PLAYER_BLUEPRINT`. See [architecture.md](architecture.md) for the full staged evaluation design.

```
Stage 1 (parallel, all subject×object pairs, 2 calls each):
  Movement: "Zombie cop sees [fire sword]. approach/flee/ignore" → flee
  Priority: "How strongly? ignore/mild/moderate/driven"          → mild

Stage 2 (parallel, pairs where approach OR priority>0):
  Action: "Zombie cop contacts [donut]. nothing/attack/heal/consume/push" → consume
  Conditional: amount, state modifier (add/remove), force modifier (damage only)
```

---

## Call budget

### 7-object scene, 1 autonomous object

| Phase | Calls | Wall time |
|---|---|---|
| Creation (new object) | ~19 | ~200ms |
| Behavior screening (1 call) | 1 | ~90ms |
| Behavior stage 1 (1 subject × 1 object × 2 questions) | 2 | ~60ms |
| Behavior stage 2 (~1 interesting pair, up to 4 calls) | ~3 | ~60ms |
| **Total** | **~25** | **~410ms** |

### 15-object scene, 3 autonomous objects

| Phase | Calls | Wall time |
|---|---|---|
| Creation (new object) | ~19 | ~200ms |
| Behavior screening (1 call) | 1 | ~125ms |
| Behavior stage 1 (3 subjects × 1 object × 2 questions) | 6 | ~60ms |
| Behavior stage 2 (~3 interesting pairs × ~3 calls) | ~9 | ~60ms |
| **Total (new non-autonomous)** | **~35** | **~445ms** |

If new object is autonomous, add: stage 1 (14 objects × 2 questions = 28 calls), stage 2 (~5 interesting pairs × ~3 calls = 15) = **~78 calls, ~605ms**.

All spawn integration runs during the 2-5s sprite gen window. Player sees no interaction latency.

---

## Scaling characteristics

Behavior evaluation is O(N²) in theory, but screening reduces this significantly — most pairs have no interesting interaction. Screening identifies ~10-15% of pairs as worth evaluating:

| Objects | Pairs | Screening calls | Interesting pairs (~10%) | Stage 1+2 calls |
|---|---|---|---|---|
| 7 | 21 | 7 | ~2 | ~10 |
| 15 | 105 | 15 | ~10 | ~50 |
| 30 | 435 | 30 | ~25 | ~125 |

Screening adds 1 call per new object. All evaluation runs during sprite generation (2-5s window).

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
