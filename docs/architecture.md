# V3 Architecture

## What this actually is

V2 with fewer enums, LLM-generated physics, and auto-populated interaction rules instead of hand-authored ones.

The pitch isn't "delete everything and just ask the LLM." It's: **automate the most tedious part (rule authoring) while keeping the engine infrastructure that makes the game work.**

The architecture keeps: a state system (smaller), behavior verbs (same), affordances (simpler), contradiction resolution, and cascade control. What it replaces: substance profiles with LLM-generated numbers, hand-authored rules with an LLM-populated cache, tag derivation with interaction-only states, and the single complex creator call with a graph of tiny parallel calls.

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

## Pairwise interaction cache

The core data structure. A lookup table mapping object pairs to interaction outcomes, populated by LLM calls at spawn time.

### Cache population

When a new object enters the scene, a single screening call identifies which existing objects it would interact with interestingly. Only those pairs get fully evaluated.

**Screening (1 call per new object, ~5-15 output tokens):**
```
"New object: fire sword (2kg, armor 80, hot, sharp, metal).
 Scene objects:
 1. wooden shield (3kg, armor 20, flammable, wood)
 2. rock (5kg, armor 70, stone)
 3. glass bottle (0.3kg, armor 5, fragile)
 Which would interact interestingly? List numbers."
 → "1,3"
```

The LLM sees all objects at once and makes relative judgments. Missed pairs default to "nothing happens" — low stakes, lazily evaluated on actual contact if needed.

**Full evaluation (interesting pairs only, 6 parallel calls each, 1 token, ~145ms):**
```
1. Damage to A? 0-100  (100=destroyed)
2. Damage to B? 0-100  (100=destroyed)
3. State change on A? 0-8  (0=none, 1-4=add state, 5-8=remove state)
4. State change on B? 0-8
5. Force on B? -100 to 100  (negative=pull, positive=push)
6. Instant or continuous? 0=instant 1=continuous
```

Include both objects' physics properties and active states in the prompt (input is free):
```
"[fire sword: 2kg, armor 80, hp 90, emits heat] hits 
 [wooden shield: 3kg, armor 20, hp 40]. Damage to B? 0-100"
```

The physics properties act as calibration anchors — the LLM sees armor 20 and produces consistent damage across similar targets. Force on A is engine-derived via Newton's 3rd law heuristic, not LLM-evaluated.

**A and B always refer to the first and second name in lexicographic sort order.** The engine maps collision participants to cache A/B by sorting their names. See [cache.md](cache.md) for key normalization.

### State changes and cache invalidation

When an object gains or loses a state, its cached interactions are stale — "wooden shield [BURNING]" interacts differently than "wooden shield." The engine marks affected cache entries as stale and re-evaluates them lazily: only when the pair next collides or enters field range. Most stale pairs are objects that aren't near each other and don't need re-evaluation until they actually meet.

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

**Stage 1 — Movement (parallel, all creature×object pairs, 1 token each):**

All creature behavior prompts include the scene inventory for context (input is free). This lets the LLM make contextually-aware decisions — a firefighter cares about water more when fire exists.

```
"Scene: [burning tree, bucket of water, trapped person, fire hydrant].
 Firefighter sees [burning tree]. 0=approach 1=flee 2=orbit 3=ignore"
→ 0 (approach)

"Scene: [burning tree, bucket of water, trapped person, fire hydrant].
 Firefighter sees [stone wall]. 0=approach 1=flee 2=orbit 3=ignore"
→ 3 (ignore)
```

**Stage 1b — Strength (parallel with stage 1, 1 token each):**

Same scene context as stage 1 — strength should reflect scene-aware priority, not just the pair in isolation.

```
"Scene: [burning tree, bucket of water, trapped person, fire hydrant].
 How strongly does firefighter react to [burning tree]?
 0=ignores, 25=mild interest, 50=moderate, 75=strong drive, 100=absolute priority"
→ 90
```

**Filter:** only pairs that returned approach (0) or orbit (2) continue. Flee and ignore pairs are complete — the creature never reaches the target so no outcome is needed.

**Stage 2 — Action (parallel, approaching/orbiting pairs only, 1 token each):**
Seeded with the movement decision from stage 1. Motivation is templated from the movement type (approach="wants to interact with", orbit="is cautious about") — no extra LLM call needed:
```
"Firefighter is APPROACHING [burning tree] and wants to interact with it.
 On arrival: 0=nothing 1=damage 2=heal 3=add state 4=remove state 5=destroy 6=take"
→ 4 (remove state)
```

**Stage 3 — Parameters (parallel, actions that need them, 1 token each):**
Seeded with the action from stage 2:
```
"Firefighter will remove a state from [burning tree]. Which?
 1=burning 2=frozen 3=wet 4=electrified"
→ 1 (burning)
```

### Why staged

Each question is trivially simple because prior answers provide context. "Firefighter removes a state from a burning tree — which state?" is a question a 1.5B model can answer. "What does a firefighter do when it encounters a burning tree? Describe the movement pattern, action type, and parameters" is much harder.

The sequential filtering also saves work. With 3 creatures × 14 objects = 42 pairs in stage 1, maybe 12 survive to stage 2, and 8 need parameters in stage 3. Total: ~104 calls, all 1 token, across 3 sequential batches (~180ms).

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
Zombie cop + citizen → orbit 40, nothing (patrols)
Firefighter + burning tree → approach 90, remove burning
Firefighter + trapped person → approach 80, heal
Doctor + injured person → approach 90, heal
Cat + mouse → approach 70, destroy
Cat + ball of yarn → orbit 50, nothing
Cat + dog → flee 80
```

### New objects and re-evaluation triggers

When a new object spawns, run stages 1-3 for all existing creatures against it. When a new creature spawns, run stages 1-3 for it against all existing objects.

**Re-evaluation triggers** — re-evaluate affected creature×object pairs when:
- **Object changes state** (gains burning, frozen, etc.) — re-evaluate pairs involving that object, since creature reactions change (firefighter doesn't need to approach a tree that's no longer burning)
- **Creature picks up or drops an object** — re-evaluate that creature's pairs with updated context ("Firefighter [holding: bucket of water] sees burning tree" → approach with higher strength)
- **Scene inventory changes** — since creature behavior prompts include the scene list, new objects or destroyed objects change the context for all creatures

Re-evaluation is lazy: fires on the creature's next behavior tick (~1s), not immediately on state change. Only nearby creatures (within perception range) are re-evaluated.

---

## Cascade control

State changes from interactions can cascade (fire spreads to nearby wood). Same controls as V2:

- **Depth limit:** max 3 levels of cascade
- **Dedup:** pair key `(id_a, id_b)` can't fire twice in one cascade chain
- **No recursive triggers:** state changes from cascaded interactions don't trigger further cascades
- **Field rate limit:** field effects tick every 2s, not every frame
- **State contradictions:** adding burning removes frozen and wet automatically (engine-enforced, see [engine-primitives.md](engine-primitives.md))

---

## What's genuinely new vs V2

1. **LLM-populated interaction cache** — replaces 56 hand-authored rules with unlimited auto-generated pairs. Cop+donut, vampire+garlic, mongoose+cobra all work without anyone coding them.

2. **LLM-generated physics** — a "fiery ice sword" gets reasonable mass/bounce/friction without substance mixing. A "thought bubble" gets mass 0.001 and floats.

3. **Graph-based creator** — parallel 1-token calls instead of 1 complex call. Faster, more reliable, works on smaller models.

4. **Per-pair creature behavior** — firefighter extinguishes fire, rescues people, chases arsonists. Each creature×object relationship gets its own movement + outcome via staged LLM evaluation. Replaces fixed verb classification.

5. **No creator-assigned tags** — objects are born stateless. All states come from interactions.

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

`RuleResolver` (V2's static rule matching) is replaced by cache lookups. Same interface shape — `resolve(obj_a, obj_b) -> list[Effect]` — but reads from the pairwise cache instead of hand-authored rules. See [cache.md](cache.md) for the cache design.

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
