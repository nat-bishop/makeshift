# Design Doc: Question-Based Object System (V3)

## What this actually is

V2 with fewer enums, LLM-generated physics, and auto-populated interaction rules instead of hand-authored ones.

The architecture keeps: a state system (smaller), behavior verbs (renamed), affordances (replaces categories), contradiction resolution, and cascade control. What it replaces: substance profiles with LLM-generated numbers, hand-authored rules with LLM-populated cache, tag derivation with interaction-only states, and the single complex creator call with a graph of tiny calls.

The pitch isn't "delete everything and just ask the LLM." It's: **automate the most tedious part (rule authoring) while keeping the engine infrastructure that makes the game work.**

See [local-llm-rules.md](local-llm-rules.md) for inference benchmarks. Key constraints:
- ~55ms base cost per call, input tokens are free
- ~7ms per output token — use numbered choices, not words
- Up to 8 parallel calls ≈ cost of 1 call
- 32 concurrent calls before GPU saturation

---

## Engine primitives

### Physics properties (set at creation, used every frame)

Each question outputs 1 number. All asked in parallel. Calibration examples go in the prompt (input is free).

| Property | Prompt format | Output |
|---|---|---|
| **Mass** (kg) | "How heavy in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500, house=50000)" | 1 number |
| **Height** (meters) | "How tall in meters? (ant=0.01, mouse=0.05, sword=1.2, human=1.7, horse=2, house=8)" | 1 number |
| **Friction** (0-100) | "How grippy 0-100? (ice=0, metal=30, wood=50, rubber=90)" | 1 number |
| **Bounce** (0-100) | "How bouncy 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)" | 1 number |
| **Gravity** (0-100) | "Gravity pull 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75)" | 1 number |

Engine maps gravity 0-100 to gravity_scale -1.0 to 2.0. Handles "gently rising smoke" (15) vs "floating ghost" (30) vs "heavy anvil" (75).

All physics values clamped to sane ranges. Mass: 0.001-100000kg. Height: 0.01-50m. Values used as-is from LLM (no quantization — cliff effects from rounding are worse than raw variance).

**Damping** derived from mass and height, not LLM-decided: `damping = height / (mass + 0.1)`. Light large things (feather) have high damping. Heavy small things (bullet) have low damping.

**Dropped from V2:** Substance enum, element enum, SUBSTANCE_PROFILES, ELEMENT_TRAITS, substance state (solid/liquid/gas/energy). Physics come from numbers, not material categories.

### Destructibility

Three questions, parallel with physics batch:

```
"Can this be destroyed? 0=no 1=yes"                                       → 1
"Armor 0-100? (paper=0, cloth=10, wood=30, steel=80, diamond=99)"         → 30
"HP 0-100? (fly=5, glass vase=15, human=50, oak tree=70, castle wall=95)" → 40
```

Indestructible objects skip damage tracking entirely. For destructible objects, armor reduces incoming damage: `effective_damage = raw_damage × (1 - armor/100)`. HP is the health pool — effective damage subtracts from it.

This separates resistance from health. A slime: armor 5 (easy to cut), HP 60 (lots of blob). A diamond: armor 99 (nearly impervious), HP 20 (shatters if breached). A paper wall: armor 0, HP 5. Each is 1 token.

### States (closed vocabulary, ~12)

Interaction-only state modifiers. Never set at creation — objects are born stateless. Applied by interaction outcomes, removed by other interactions or decay timers.

Default state duration: 10s. Refreshed while the source persists (standing in fire = on_fire refreshes every 2s from field tick). Permanent states only from permanent sources.

Non-contradicting states stack: an object can be `on_fire + poisoned + weakened` simultaneously. Visual stacking: particles layer additively, tints multiply, most recent shader wins.

Numbered for LLM output:

| # | State | Visual effect | Contradicts |
|---|---|---|---|
| 0 | none | — | — |
| 1 | on_fire | Fire particles + orange PointLight2D | frozen, wet |
| 2 | frozen | Blue tint + ice shader | on_fire, molten |
| 3 | wet | Drip particles | on_fire |
| 4 | electrified | Spark particles + periodic flash | — |
| 5 | poisoned | Green particles + green tint | — |
| 6 | corroded | Brown tint + crumble particles | — |
| 7 | molten | Orange glow + ripple shader | frozen |
| 8 | blessed | Gold particles + glow | cursed |
| 9 | cursed | Dark particles + desaturation | blessed |
| 10 | weakened | Dim + shrink pulse | strengthened |
| 11 | strengthened | Bright + grow pulse | weakened |
| 12 | petrified | Grey tint + no animation | molten |

Contradiction table is static (~8 pairs). Engine enforces on state add — adding on_fire removes frozen and wet automatically.

**Why closed, not freeform:** Freeform descriptors ("burning" vs "on fire" vs "ablaze") break the cache, prevent contradiction resolution, and require sprite regeneration. Closed vocabulary with numbered output: 1 token, deterministic cache key, known visual treatment, no sprite regen needed.

### Fields

Two creation-time questions:
```
"Does this affect nearby things without touching? 0=no 1=yes" → 1
"If yes, range in meters? (candle=0.5, campfire=2.5, volcano=10)" → 2.5
```

The engine creates an Area2D with that radius. Field interactions use the same pairwise cache as contact interactions — no separate system. Field ticks every 2s.

### Affordances

Each is engine code. Numbered for LLM multi-select:

```
"Which apply? Comma-separated numbers.
 0=holdable 1=climbable 2=rideable 3=shootable
 4=attachable 5=containable 6=openable 7=wearable"
→ "0" (sword: holdable)
→ "0,3" (bow: holdable + shootable)
```

| # | Affordance | Engine mechanic |
|---|---|---|
| 0 | **holdable** | Pick up, carry, swing/use |
| 1 | **climbable** | Player moves upward while overlapping |
| 2 | **rideable** | Player attaches, controls movement |
| 3 | **shootable** | Produces projectiles when activated |
| 4 | **attachable** | Physics joint between objects/surfaces |
| 5 | **containable** | Holds other objects inside |
| 6 | **openable** | Toggle open/closed state |
| 7 | **wearable** | Equip to slot, modify stats |

Follow-up questions for selected affordances (1-2 tokens each):
- Shootable → "Projectile speed 0-100? Range 0-100? 0=manual 1=auto?"
- Attachable → "Length in meters? Break force 0-100?"

List grows as engine adds mechanics. Each new affordance = engine code + new number.

Some interactions are affordance + interaction outcome, not separate affordances:
- Drinkable/edible = holdable + pairwise interaction with player → heal
- Throwable = holdable + release physics (parameter on holdable, not separate affordance)
- Pushable = mass too high for pickup → engine applies force instead of attach

### Held object rules

Held objects have special interaction behavior:

- **Contact interactions suppressed.** Carrying a fire sword does NOT burn everything you walk past. Passive pairwise cache interactions are disabled while held.
- **Field effects still active.** A held torch still emits heat in a radius. Fields are continuous area effects, not contact events.
- **Use action triggers pairwise cache.** Player presses "use" → engine looks up pairwise interaction between held object and the target the player is facing. Fire sword "used" on wooden wall → cache lookup → damage + on_fire. Explicit, not accidental.
- **Creature intent overrides.** When a creature reaches a target via behavior verb, the verb determines outcome (eat = consume, destroy = attack), not the passive pairwise cache.

---

## Two interaction systems (not one)

This is the key architectural distinction. Passive collisions and intentional actions produce different outcomes for the same pair.

### Passive interactions (pairwise cache) — "what happens when objects collide"

Physics-driven. Object A bumps into object B. Nobody intended it.

Populated at spawn time, per scene object pair. Each pair gets 6 parallel 1-token calls:

```
"[fire sword: 2kg, emits heat, armor 90, hp 80] hits 
 [wooden shield: 3kg, armor 30, hp 40]. Damage to A? 0-100"        → 0
"Same. Damage to B? 0-100"                                          → 40
"Same. State change to B? 0-12 (0=none 1=on_fire 2=frozen ...)"    → 1
"Same. Force on B? 0-100 (0=none)"                                  → 20
"Same. Force direction? 0=none 1=push_away 2=pull_toward"           → 1
"Same. 0=instant 1=continuous"                                       → 1
```

6 parallel calls, 1 token each, ~60ms per pair.

This handles: fire burns wood, water extinguishes fire, acid corrodes metal, garlic damages vampire. All physics/chemistry/folklore — things that happen regardless of intent.

### Cache keys include states

Cache key: `(object_a_name + sorted_states, object_b_name + sorted_states)`.

"Wooden shield" and "wooden shield [on_fire]" are separate cache entries. In practice, objects have 0-2 states at any time, and contradictions prevent most stacking (on_fire removes wet and frozen). Typical variants per object: base + 2-3 common state combinations.

Pre-cache strategy at spawn: if fire is in the scene, also pre-cache `[on_fire]` variants for all flammable-seeming objects. Lazy eval catches rare combinations.

### Intentional actions (behavior system) — "what creatures do on purpose"

Creature-driven. A zombie DECIDES to eat a brain. A guard dog DECIDES to protect the player. Intent determines outcome, not just contact.

**Behavior verbs** (movement patterns with intent):

| # | Verb | Movement | On reaching target |
|---|---|---|---|
| 0 | **destroy** | Approach | Attack (damage target, amount from pairwise cache) |
| 1 | **eat** | Approach | Consume (destroy target, heal self proportional to target's HP) |
| 2 | **investigate** | Orbit/approach slowly | Idle near target, lose interest after ~10s |
| 3 | **follow** | Maintain distance | Track without engaging |
| 4 | **guard** | Stay near target | Attack threats to target (requires threat tracking) |
| 5 | **flee** | Run away | — |

**Guard requires a threat-tracking subsystem:**
The guard verb isn't just "stay near target." It's a state machine:
1. **Guarding:** Stay within range of guarded entity. Idle.
2. **Engaging:** Something damaged the guarded entity → approach aggressor, attack.
3. **Returning:** Aggressor eliminated or left range → return to guard position.

Implementation: maintain an aggressor list per guarded entity (who damaged it recently, ~10s memory). Prioritize by recency. This is ~50-80 lines of engine code with its own state machine. Not one-line behavior.

**Behavior format** (compact, ~2-3 tokens per entry):

```
"What does a zombie cop do? Up to 5.
 Format: verb_number,strength,target
 Verbs: 0=destroy 1=eat 2=investigate 3=follow 4=guard 5=flee"
→ 1,80,brains
  1,90,donuts
  0,60,living humans
  5,70,fire
```

**Why both systems exist:**

Zombie touches sword (passive collision, kicked at zombie): pairwise cache → sword damages zombie.
Zombie reaches sword (intentional, "investigate weapon"): behavior verb → zombie picks it up (holdable affordance check).
Same pair, different outcome. Intent is the difference.

The engine distinguishes: collision events → pairwise cache. Behavior target reached → verb handler. No ambiguity.

### Behavior target matching

Creature has: "eat,90,donuts". New object: "glazed pastry." LLM call:

```
"Is 'glazed pastry' a match for target 'donuts'? 0=no 1=yes" → 1
```

Cached by (target_string, object_name). All zombies targeting "donuts" share the same match cache.

Matching is transparent to the player: when a creature targets something, its target list is visible (debug overlay or UI hint: "The zombie cop wants: donuts, brains, living humans"). The player sees what matches and can reason about it. If the LLM inconsistently matches an edge case, the cached result sticks — consistency after first evaluation.

### Autonomous flag

```
"Does this act on its own? (moves, makes decisions) 0=no 1=yes" → 1
```

Not "is it alive?" — "is it autonomous?" A robot: yes. A sentient sword: yes. A tree: no. A campfire: no (has a field, but doesn't navigate or target). A turret with auto-aim: no (handled by shootable affordance with auto parameter, not behavior system).

---

## Object creation flow

```
"fire sword"

=== Batch 1: Properties (parallel, ~60ms) ===
10 calls, all 1-token output:
- Mass, height, friction, bounce, gravity
- Destructible? Armor? HP?
- Autonomous?
- Has field? Range?

=== Batch 1b: Concurrent with batch 1 (~200ms) ===
- Visual description (~20-30 tokens)
- Affordances (1-3 tokens)

=== Batch 2: Conditional (~60-190ms) ===
- If autonomous: behavior list (~15-20 tokens)
- If shootable: projectile params (3 tokens)

=== Batch 3: Spawn interactions (parallel, hidden behind sprite gen) ===
Per scene object pair, 6 parallel calls each (1 token):
- Damage to A, damage to B, state change, force, direction, mode

Pre-cache common state variants for objects in scene.
If autonomous: behavior target matching (1 token per target×object name)

=== Background: Sprite generation (2-5s) ===
- Image gen from visual description
- BG removal + crop
```

Batch 3 runs entirely during the 2-5s sprite gen window. Player sees no interaction latency.

### Projectiles

Projectiles are lightweight — not full objects. Created by the shootable affordance. Properties:
- Mass, speed, gravity (from shootable follow-up questions)
- Damage (from pairwise cache: projectile type vs target)
- No affordances, no behaviors, no states
- No full creation flow — skips batches 1/1b/2

---

## Cascade control

State changes from interactions can cascade (fire spreads to nearby wood). Same controls as V2:

- **Depth limit:** max 3 levels of cascade
- **Dedup:** pair key (id_a, id_b) can't fire twice in one cascade chain
- **No recursive triggers:** state changes from cascaded interactions don't trigger further cascades
- **Field rate limit:** field effects tick every 2s, not every frame

**Lazy cache invalidation:** when an object gains a state, mark its cached pairs as stale. Don't re-evaluate eagerly against all scene objects. Re-evaluate lazily: when the stale pair next interacts (contact or field tick), check staleness, re-evaluate then. Cost drops from O(N) per change to O(K) where K = objects currently near the changed object.

---

## What V3 replaces from V2

| V2 system | V3 replacement | What changed |
|---|---|---|
| 16 substances + profiles | LLM-generated physics numbers | No material enum, LLM reasons about blends |
| 7 elements + traits | Part of object description | No element enum |
| 7 categories | Affordances (0-7) + autonomous flag | "What you can do with it" not "what it is" |
| 31 tags (10 LLM-visible + 21 internal) | ~12 interaction states (closed) | States only from interactions, never creator |
| 16 contradiction pairs | ~8 state contradiction pairs | Smaller, same mechanism |
| 56 hand-authored rules | LLM-populated pairwise cache | Auto-generated, handles infinite pairs |
| Tag derivation pipeline | Not needed | States aren't derived from identity |
| Combat profiles | Pairwise cache damage values + armor/HP | Per-pair, not per-substance |
| Single complex creator call (~130 tokens) | Graph of parallel tiny calls (~15 tokens for properties) | 37% faster, more reliable |
| BEHAVIOR_TARGETS enum (9 values) | Freeform target strings, LLM-matched | "donuts" not "FOOD" |

## What V3 keeps from V2

| System | Why it survives |
|---|---|
| Behavior verbs (6, renamed) | Intent determines outcome — passive collision ≠ intentional action |
| State contradiction table | Engine must enforce "on_fire removes wet" mechanically |
| Cascade depth + dedup | Prevents infinite state ping-pong |
| Collision detection + Area2D | Engine decides WHEN things meet |
| Physics simulation | Per-frame, can't wait for LLM |
| Image pipeline | Sprite gen, bg removal |
| WebSocket delivery | Client communication |
| Session persistence | Save/restore |
| State→visual effect mapping | Hand-authored, ~12 entries, purely cosmetic |

---

## What's genuinely new

1. **LLM-populated interaction cache** — replaces 56 hand-authored rules with unlimited auto-generated pairs. Cop+donut, vampire+garlic, mongoose+cobra all work without anyone coding them.

2. **LLM-generated physics** — a "fiery ice sword" gets reasonable mass/bounce/friction without a substance mixing formula. A "thought bubble" gets mass 0.001 and floats. No 16-substance constraint.

3. **Graph-based creator** — 10 parallel 1-token calls instead of 1 complex 130-token call. Faster, more reliable, works on smaller models.

4. **Freeform behavior targets** — "seek donuts" instead of "seek FOOD." Semantic matching via cached LLM calls. Transparent to player.

5. **No creator-assigned states** — objects are born stateless. All states come from interactions. Simpler creator, cleaner separation of identity vs condition.

6. **Armor + HP separation** — two numbers instead of one toughness value. Enables "low armor high health" (slime) and "high armor low health" (diamond).

---

## Open questions

**Cache miss on first contact.** If precomputation missed a pair, synchronous eval takes ~100ms (6 frames). For passive collisions, apply generic physics response (mass-based knockback) immediately, evaluate interaction async, apply result next tick. For behavior-triggered actions, the creature's approach animation provides natural buffer time.

**Cross-pair damage consistency.** Fire sword does X to wooden shield and Y to wooden door. Including armor/HP in the prompt helps (both have armor 30 → similar damage reduction). But no guarantee of identical results. The substance system's determinism is genuinely lost. Acceptable tradeoff for a creative sandbox — slight variance feels natural.

**Creation consistency.** Two "fire swords" may get different mass. Fix: cache creation results by object name. First "fire sword" → mass 2.0. All subsequent get 2.0 from cache. "Big fire sword" vs "fire sword" still varies (this is correct — they're different objects).

**Behavior matching cost.** Unique_targets × unique_object_names matching calls at spawn. With 8 unique targets and 15 objects: 120 calls. At 8 parallel: 15 batches × 60ms = 900ms. Hidden behind sprite gen but tight. May need coarser pre-filtering: "Is anything nearby relevant to any of this creature's targets?" as a single screening call.

**Prompt maintenance.** ~15 prompt templates with calibration examples. Stored in one config file. Need re-tuning when model changes. Real cost, but less than maintaining 56 rules + substance profiles + tag derivation.

**Balance.** All numbers from the LLM. Calibration examples set the scale. No global balance constraint. May need post-hoc validation: flag pairwise results where effective damage > HP (one-shot kills) for review.

**State variant pre-caching.** At spawn, pre-cache common state variants (base + on_fire + frozen + wet) for objects likely to gain those states. Heuristic: if scene contains fire sources, pre-cache on_fire variants for destructible objects. Misses are handled by lazy eval.
