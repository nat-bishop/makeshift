# V3 Creation Pipeline

The exact sequence of LLM calls from player input to spawned object. All call counts assume the model and prompt formats from [local-llm-rules.md](local-llm-rules.md).

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

=== Batch 2: Conditional (~60-190ms, only if needed) ===
14. If autonomous: behavior list  → verb,target entries (~15-20 tokens)

Total creation calls: 13-14
Total output tokens: ~15 for properties + ~25 for visual + ~15 for behaviors = ~55
Wall time: ~200ms (batches 1+1b in parallel, batch 2 if needed)
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

### Movement reactions (autonomous creatures only)

For every autonomous creature in the scene, evaluate its reaction to the new object:

```
Per creature × new object (1 call, 2 tokens):
"Zombie cop sees [fire sword: flaming longsword with ember particles]. 
 0=approach 1=flee 2=orbit 3=ignore. Strength 0-100?"
→ 1, 70 (flee, fire)
```

Also: if the NEW object is autonomous, evaluate its reaction to every existing object.

### State-based interaction table

For every object in the scene, evaluate its interaction with each of the 7 states:

```
Per object × 7 states, 3 parallel calls (1 token each):
"An on_fire object is near [wooden chair: 1kg, armor 20, hp 30]. 
 Damage? 0-100"     → 20
"State change? 0-7"  → 1 (on_fire)
"Mode? 0=instant 1=continuous" → 1
```

This provides categorical state interactions (fire burns wood) without runtime LLM calls. See [architecture.md](architecture.md) for why this exists.

### Destruction results

After pairwise cache is populated, scan for DESTROY outcomes. For each destruction path:

```
Per destruction path (1 call, ~5 tokens):
"A [wooden shield] destroyed by [fire]. What remains? 3-5 words."
→ "pile of charred splinters"
```

Then in background: run creation graph for the remains + generate sprite. Not a fixed cost — scales with actual destruction paths in the scene.

---

## Call budget

### 7-object scene, 1 creature

| Phase | Calls | Tokens | Wall time |
|---|---|---|---|
| Creation (new object) | 13 | ~40 | ~200ms |
| Passive pairwise (6 pairs) | 30 | 30 | ~240ms |
| State interaction table (1 new object × 7 states × 3 calls) | 21 | 21 | ~180ms |
| Movement reactions (1 creature × 1 new object) | 1 | 2 | ~60ms |
| Destruction results (~2 paths) | 2 | ~10 | ~60ms |
| **Total** | **67** | **~103** | **~740ms** |

### 15-object scene, 3 creatures

| Phase | Calls | Tokens | Wall time |
|---|---|---|---|
| Creation (new object) | 14 | ~55 | ~200ms |
| Passive pairwise (14 pairs with new object) | 70 | 70 | ~540ms |
| State interaction table (1 new object × 7 states × 3 calls) | 21 | 21 | ~180ms |
| Movement reactions (3 creatures × 1 new) | 3 | 6 | ~60ms |
| Movement reactions (if new is creature: 1 × 14 objects) | 14 | 28 | ~120ms |
| Destruction results (~3 paths) | 3 | ~15 | ~60ms |
| **Total (new non-creature)** | **111** | **~167** | **~1,040ms** |
| **Total (new creature)** | **125** | **~195** | **~1,160ms** |

All spawn integration runs during the 2-5s sprite gen window. Player sees no interaction latency.

### Full scene initialization (15 objects from scratch)

| Phase | Calls | Tokens |
|---|---|---|
| Creation (15 objects) | 15 × 13 = 195 | ~600 |
| Passive pairwise (105 pairs) | 105 × 5 = 525 | 525 |
| State interaction table (15 objects × 7 states × 3 calls) | 315 | 315 |
| Movement reactions (3 creatures × 14 objects) | 42 | 84 |
| Destruction results (~10 paths) | 10 | ~50 |
| **Total** | **1,087** | **~1,574** |

At 8 parallel, 60ms per batch: ~136 batches × 60ms = **~8.2 seconds**. This is scene load time, not per-object. Runs once when the level starts.

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
2. **Destruction results:** Only generated for destruction paths that exist in the current scene. Background image gen, non-blocking.
3. **Sprite cache:** Keyed by SHA-256 of description. Identical descriptions share sprites across sessions.

---

## Open questions

**Interaction call format.** The 5-call-per-pair format (damage A, damage B, state, force, mode) needs prompt testing with the actual LLM. May need to split differently or combine some fields.

**Balance.** All numbers from the LLM. Calibration examples set the scale. No global balance constraint. May need post-hoc validation: flag results where damage > HP (one-shot kills) for review.

**State interaction table granularity.** Currently evaluated as "an on_fire object near [X]" — no distinction between a burning wall and a burning sword. This matches V2's behavior (HEAT_SOURCE is HEAT_SOURCE) but loses specificity. May need refinement if players expect different heat intensities from different burning objects.
