# V3 Architecture

## What this actually is

V2 with fewer enums, LLM-generated physics, and auto-populated interaction rules instead of hand-authored ones.

The pitch isn't "delete everything and just ask the LLM." It's: **automate the most tedious part (rule authoring) while keeping the engine infrastructure that makes the game work.**

The architecture keeps: a state system (smaller), affordances (simpler), and contradiction resolution. What it replaces: substance profiles with LLM-generated numbers, hand-authored rules with an LLM-populated cache, tag derivation with interaction-only states, cascade + ObjectField with tick-based StatePropagator, and the single complex creator call with a graph of tiny parallel calls.

See [llm-design-patterns.md](llm-design-patterns.md) for inference constraints. Key numbers:
- ~55ms base cost per call, input tokens are free
- ~7ms per output token — use numbered choices, not words
- 8 parallel calls ≈ 2.2x cost of 1 call (not 8x)
- 32 concurrent calls before GPU degradation — fire all via `asyncio.gather()`, let SGLang batch internally

---

## Two interaction systems

This is the key architectural idea. The same two objects can produce different outcomes depending on HOW they meet.

### Passive interactions — "what happens when objects collide"

Physics-driven. Object A bumps into object B. Nobody intended it. The engine resolves it from the cached LLM evaluation.

**Examples:**
- Fire sword falls onto wooden shield → damage 40, add state burning
- Rock rolls into glass bottle → damage 60, destroy bottle
- Water splashes onto campfire → remove burning state, destroy water

The LLM is asked at spawn time: "fire sword hits wooden shield, what happens?" The answer is cached. At runtime, the engine just looks it up. No LLM call during gameplay.

### Intentional interactions — "what creatures do on purpose"

Creature-driven. A zombie DECIDES to eat a brain. A guard dog DECIDES to protect the player. Intent determines the movement pattern, and the behavior verb determines what happens on contact.

**Examples:**
- Zombie (eat verb) reaches brain → destroy brain, heal zombie
- Guard dog (guard verb) stays near player → attacks threats to player
- Cat (investigate verb) approaches ball of yarn → idles nearby

**Why both systems exist:**

Zombie touches sword (passive collision — sword was kicked at zombie): pairwise cache → sword damages zombie.

Zombie reaches sword (intentional — zombie investigating the weapon): behavior verb → zombie picks it up (if holdable).

Same pair, different outcome. Intent is the difference. The engine distinguishes: collision events → pairwise cache. Behavior target reached → verb handler.

---

## Collision cache

A lookup table mapping object pairs to force-only collision rules, populated by LLM calls at spawn time.

### Cache population

When a new object enters the scene, a single screening call identifies which existing objects it would have interesting force interactions with. Only those pairs get evaluated.

**Screening (1 call per new object, pre-warming only — not a gate):**
```
"New object: fire sword (2kg, normal, durability normal).
 Scene objects:
 1. wooden shield (3kg, normal, durability normal)
 2. rock (5kg, normal, durability tough)
 3. glass bottle (0.3kg, normal, durability soft)
 Which would have interesting physical force interactions
 (pushing, pulling, magnetism, wind, repulsion) with fire sword? → "none"
```

Missed pairs are lazily evaluated on actual collision via `request_collision` WS message.

**Force evaluation (1 call per interesting pair):**
```
"fire sword (2kg, 120cm, normal, normal-surface) contacts
 magnet (0.5kg, 10cm, normal, normal-surface).
 Does the first push or pull the second?
 none / pull / drag / push / throw"
→ "pull"
```

Force categories map to signed values: none=0, pull=-30, drag=-80, push=30, throw=80.

**A and B always refer to the first and second name in lexicographic sort order.** See [cache.md](cache.md) for key normalization.

### State changes and collision rules

Collision rules are permanent — gaining or losing a state does NOT re-evaluate `CollisionRule` entries. Force between objects is a material property, not state-dependent. State-based interactions (fire spreading to wood) are handled by `initial_states`/`susceptible_states` on each object and tick-based propagation, not by pairwise cache lookup.

---

## Creation cache

Separate from the interaction cache. Maps object names to their creation-time LLM answers (physics, affordance, destructibility, field, autonomous, behaviors).

First "fire sword" → mass 2.0, affordance carry, etc. All subsequent "fire sword" creations return the same values. This is a correctness requirement, not optimization — two identical objects should have identical physics. Without this, players can't predict what they're creating.

Exact name match only. "Fire sword" and "big fire sword" are different cache entries — they're different objects.

---

## Creature behavior — per-pair evaluation

Replaces both behavior verbs AND seek/avoid targeting from V2. Instead of classifying a creature into fixed verbs at creation ("firefighter investigates fire") and then separately evaluating movement at spawn, evaluate BOTH movement and outcome per creature×object pair.

A firefighter doesn't have one behavior. It extinguishes fire, rescues people, and chases arsonists. The LLM decides what the creature does with EACH specific thing it encounters.

### Staged evaluation (sequential + parallel)

Follows the graph thesis: simple questions, 1 token each, sequential stages that seed context forward.

**Stage 1 — Movement + Priority (parallel, all creature×object pairs, 2 calls per pair):**

All creature behavior prompts include the scene inventory for context (input is free). This lets the LLM make contextually-aware decisions — a firefighter cares about water more when fire exists. State context included for re-eval after `state_changed`.

```
"Scene: [burning tree, bucket of water, trapped person, fire hydrant].
 Firefighter sees [burning tree].
 → approach / flee / ignore"
→ approach

"Scene: [burning tree, bucket of water, trapped person, fire hydrant].
 How strongly does Firefighter react to [burning tree]?
 → ignore / mild / moderate / driven"
→ driven
```

**Filter:** only pairs that returned approach (0) continue to stage 2. Flee and ignore pairs are complete.

**Stage 2 — Action (parallel, approaching pairs only, 1 call per pair):**
```
"Firefighter is approaching [burning tree] and wants to interact with it.
 → nothing / attack / heal / ignite / cleanse / consume"
→ cleanse
```

**Stage 3 — Parameters (parallel, actions needing them: attack/heal/ignite/cleanse):**
```
"Firefighter will cleanse a state on [burning tree].
 → burn / freeze / wet / zap"
→ burn
```

### Why staged

Each question is trivially simple because prior answers provide context. The sequential filtering saves work: with 3 creatures × 14 objects = 42 pairs in stage 1, maybe 12 survive to stage 2, and 8 need parameters in stage 3. All 1-token choices, 3 sequential batches.

### What this replaces

| V2 | Per-pair behavior |
|---|---|
| 6 behavior verbs (creation-time) | Dropped — outcomes are per-pair, not per-creature |
| Seek/avoid target strings | Dropped — no freeform targets, no semantic matching |
| BEHAVIOR_TARGETS enum (9 values) | Dropped — LLM evaluates each specific object directly |
| Fixed creature classification | Each creature×object pair gets its own movement + outcome |

### Examples

```
Zombie cop + donut → approach 90, destroy + heal (eats it)
Zombie cop + criminal → approach 80, damage
Zombie cop + fire → flee 70
Zombie cop + citizen → ignore 40
Firefighter + burning tree → approach 90, remove burning
Firefighter + trapped person → approach 80, heal
Doctor + injured person → approach 90, heal
Cat + mouse → approach 70, destroy
Cat + ball of yarn → approach 50, nothing
Cat + dog → flee 80
```

### New objects and re-evaluation triggers

When a new object spawns, run stages 1-3 for all existing creatures against it. When a new creature spawns, run stages 1-3 for it against all existing objects.

**Re-evaluation on state change:** when `state_changed` WS message arrives, `_handle_state_changed()` in `ws/handler.py`:
1. Invalidates all behavior entries involving the changed object (`BehaviorCache.invalidate_behavior()`)
2. Re-evaluates all creatures toward the changed object (with `target_states` dict in prompts)
3. If the changed object is itself a creature, re-evaluates its outgoing behaviors

Results delivered via `behavior_updated` WS message. Client updates `InteractionCache._behavior` dict in place.

---

## State propagation (replaces cascade + ObjectField)

State spreading is handled by `StatePropagator` — a tick-based (2s) area component on every game object. When an object has active states, it periodically checks nearby bodies and spreads states to `susceptible_states` neighbors.

- **Tick interval:** 2s. First tick is immediate on state added.
- **Radius:** `BASE_RADIUS × scale_from_height(height_cm)` — larger objects spread further.
- **Susceptibility:** only spreads if target has the state ID in its `susceptible_states` list.
- **State contradictions:** enforced by `StateManager.add_state()` — adding burning removes frozen and wet automatically.
- **No cascade depth limit:** propagation doesn't chain recursively — each tick is independent.

**Essential-state destruction** replaces the old "LLM decides destroy." If an object's `initial_states` are all removed via contradiction (e.g., fire [burning] is hit by water → burning removed), `take_damage(99999)` is called immediately. No LLM call, no `damage=100` pairwise field.

---

## What's genuinely new vs V2

1. **LLM-populated collision + behavior cache** — replaces 56 hand-authored rules. Cop+donut, vampire+garlic, mongoose+cobra all work without anyone coding them.

2. **LLM-generated physics** — a "fiery ice sword" gets reasonable mass/bounce/friction without substance mixing. A "thought bubble" gets mass 0.001 and floats.

3. **Graph-based creator** — parallel 1-token calls instead of 1 complex call. Faster, more reliable, works on smaller models.

4. **Per-pair creature behavior** — firefighter extinguishes fire, rescues people, chases arsonists. Each creature×object relationship gets its own movement + outcome via staged LLM evaluation. Replaces fixed verb classification.

5. **State properties replace ObjectField** — `initial_states`/`susceptible_states` on blueprint replace `has_field`/`field_range_cm`. Fire spawns with burning state; wood is susceptible to burning. `StatePropagator` ticks every 2s and spreads states to susceptible neighbors.

6. **Essential-state destruction** — objects with `initial_states` are destroyed when all their initial states are removed. No pairwise "damage=100" for fire/ice destruction — it's structural.

---

## Implementation decisions

### The creation pipeline is not a graph

The parallel LLM calls are a **fan-out/fan-in** pattern, not a DAG or state machine. 13 independent calls fire in parallel, results are assembled, then a conditional batch runs if the object is autonomous. There's no branching, no cycles, no node-to-node data flow.

**pydantic-ai Graph is the wrong tool.** It's a finite state machine — nodes execute sequentially, each node's return type picks the next node. No built-in parallelism. Using it would mean stuffing all parallel calls inside a single node's `run()` method, making the Graph wrapper pure boilerplate.

**Use `asyncio.gather()`** for fan-out. It supports per-call error handling via `return_exceptions=True`, which is what we want — if one call fails, retry it individually rather than canceling the others.

### Data-driven question lists

Define LLM calls as data, not code. The orchestration is generic — to add, remove, or edit a property during playtesting, edit the question list:

```python
CREATION_QUESTIONS = [
    Question(key="mass",    prompt="How heavy is {name} in kg? (ant=0.001, sword=1.5, car=1500)", max_tokens=4),
    Question(key="height",  prompt="How tall is {name} in cm? (ant=1, sword=120, human=170, house=800)", max_tokens=2),
    Question(key="friction", prompt="How grippy is {name} 0-100? (ice=0, rubber=90)", max_tokens=1),
    # ... add/remove/edit lines here during playtesting
]

async def create_object(name: str) -> dict:
    results = dict(await asyncio.gather(*[
        ask(q.prompt.format(name=name), q.max_tokens) for q in CREATION_QUESTIONS
    ]))
    if results["autonomous"] == "1":
        results["behaviors"] = await ask_behaviors(name)
    return results
```

Same pattern for pairwise interaction calls and creature behavior stage calls.

### No client-side rate limiting

SGLang uses continuous batching — it internally queues requests and schedules them across GPU resources, batching prefill and decode phases independently. This is smarter than a client-side semaphore that treats all calls as equal-cost.

Fire all requests concurrently. SGLang handles scheduling. If overloaded, it returns 503 — handle with retry (PydanticAI has built-in retry).

### LLM client — PydanticAI for everything

Use PydanticAI agents for all LLM calls to start. One system, consistent API. For 1-token calls, use `Agent` with `output_type=int` and `max_tokens=1`.

See [future-optimizations.md](future-optimizations.md) for a potential raw httpx + SGLang constrained decoding path if parsing failures become a problem.

### Interaction resolver — cache-backed

The static `RuleResolver` is replaced by `InteractionCache` (Godot autoload) and `BehaviorCache` (backend in-memory). `CollisionResolver` calls `InteractionCache.lookup_collision(a, b)` and applies force; on miss, it calls `request_collision_eval()` to trigger lazy LLM eval. See [cache.md](cache.md) for the cache design.

### Library decisions

| Library | Decision | Reason |
|---------|----------|--------|
| pydantic-ai Graph | Skip | FSM, not a parallel runner — wrong abstraction |
| asyncio.gather | Use | Fan-out/fan-in with per-call error handling |
| PydanticAI agents | Use | Consistent API for all LLM calls |
| aiosqlite | Keep | Already using; works for both game.db and cache.db |
| diskcache | Skip | Sync-only — every read needs `run_in_executor()` in async code |
| aiocache | Skip | No SQLite backend; needs Redis for persistence (overkill for local-first) |
| stamina | Skip for now | PydanticAI has built-in retry; revisit if using raw httpx later |
| SGLang constrained decoding | Future | Log as optimization, don't implement yet |
