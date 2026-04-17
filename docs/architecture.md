# Architecture

The core idea: **automate rule authoring with LLM calls while keeping the engine infrastructure that makes the game work.** The LLM generates physics properties and populates a per-pair behavior cache at spawn time. The engine executes a state system, affordances, and contradiction resolution at runtime.

See [llm-design-patterns.md](llm-design-patterns.md) for inference constraints. Key numbers:
- ~55ms base cost per call, input tokens are free
- ~7ms per output token — use numbered choices, not words
- 8 parallel calls ≈ 2.2x cost of 1 call (not 8x)
- 32 concurrent calls before GPU degradation — fire all via `asyncio.gather()`, let SGLang batch internally

---

## Unified behavior system

One system handles all object interactions — active creatures (wolf, zombie) AND reactive objects (bomb, fan, acid). Both use the same `BehaviorEntry` (movement, priority, action, amount, state_action, state_id, force) and the same staged evaluation pipeline.

**Active objects** (`active=true`, movement=approach/flee) move toward or away from targets and execute on-arrival actions.

**Reactive objects** (`active=true`, movement=ignore, priority>0) never move but act immediately when a target enters CONTACT_RANGE. A bomb ignores everything until something touches it.

A firefighter doesn't have one behavior. It extinguishes fire, rescues people, and chases arsonists. The LLM decides what each object does with EACH specific thing it encounters.

### Staged evaluation (sequential + parallel)

Bidirectional screening (1 call per spawn) identifies interesting pairs first. Then:

**Stage 1 — Movement + Priority (parallel, all subject×target pairs, 2 calls per pair):**

All behavior prompts include the scene inventory for context (input is free). State context included for re-eval after `state_changed`.

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

**Filter:** pairs where `movement=approach OR priority>0` continue to stage 2. This captures both approaching creatures and reactive objects (ignore + high priority).

**Stage 2 — Composite action pipeline (parallel, filtered pairs, 1 call per pair):**
```
"Firefighter contacts [burning tree].
 → nothing / attack / heal / consume / push"
→ attack
```
Conditional parallel follow-ups: amount (actions 1-3), state_modifier+state_id (actions 1-3), force_modifier (damage only).

### Action enum

| # | Action | Force modifier | State modifier |
|---|---|---|---|
| 0 | nothing | — | — |
| 1 | damage | optional push | optional add/remove state |
| 2 | heal | — | optional add/remove state |
| 3 | consume | — | optional add/remove state |
| 4 | push | — | — |

Actions are composite: a wolf can damage + push (knockback) + add_state(burning) in one interaction. Force modifier (knockback) fires for damage only. Pull is not a supported force modifier.

### Examples

```
Zombie cop + donut → approach 90, consume + heal (eats it)
Zombie cop + criminal → approach 80, damage
Zombie cop + fire → flee 70
Bomb + anything → ignore + driven, damage + push (explodes on contact)
Fan + leaves → ignore + moderate, push (blows them away)
Firefighter + burning tree → approach 90, damage(remove burning)
Doctor + injured person → approach 90, heal
```

### New objects and re-evaluation triggers

When a new object spawns, run bidirectional screening then stages 1-2 for all interesting pairs. The player is always included as a potential target via `PLAYER_BLUEPRINT`.

**Re-evaluation on state change:** when `state_changed` WS message arrives, `_handle_state_changed()` in `ws/handler.py`:
1. Invalidates all behavior entries involving the changed object (`BehaviorCache.invalidate_behavior()`)
2. Re-evaluates all creatures toward the changed object (with `target_states` dict in prompts)
3. If the changed object is itself a creature, re-evaluates its outgoing behaviors

Results delivered via `behavior_updated` WS message. Client updates `InteractionCache._behavior` dict in place.

---

## Creation cache

Separate from the behavior cache. Maps object names to their creation-time LLM answers (physics, affordance, destructibility, states, active).

First "fire sword" → mass 2.0, affordance carry, etc. All subsequent "fire sword" creations return the same values. This is a correctness requirement, not optimization — two identical objects should have identical physics. Without this, players can't predict what they're creating.

Exact name match only. "Fire sword" and "big fire sword" are different cache entries — they're different objects.

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

## Implementation decisions

### The creation pipeline is not a graph

The parallel LLM calls are a **fan-out/fan-in** pattern, not a DAG or state machine. 13 independent calls fire in parallel, results are assembled, then a conditional batch runs if the object is active. There's no branching, no cycles, no node-to-node data flow.

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
    if results["active"] == "1":
        results["behaviors"] = await ask_behaviors(name)
    return results
```

Same pattern for behavior evaluation stage calls.

### No client-side rate limiting

SGLang uses continuous batching — it internally queues requests and schedules them across GPU resources, batching prefill and decode phases independently. This is smarter than a client-side semaphore that treats all calls as equal-cost.

Fire all requests concurrently. SGLang handles scheduling. If overloaded, it returns 503 — handle with retry (PydanticAI has built-in retry).

### LLM client — PydanticAI for everything

Use PydanticAI agents for all LLM calls to start. One system, consistent API. For 1-token calls, use `Agent` with `output_type=int` and `max_tokens=1`.

See [future-optimizations.md](future-optimizations.md) for a potential raw httpx + SGLang constrained decoding path if parsing failures become a problem.

### Interaction resolver — cache-backed

The static `RuleResolver` is replaced by `InteractionCache` (Godot autoload) and `BehaviorCache` (backend in-memory). `ObjectBehavior` calls `InteractionCache.lookup_behavior(subject, target)` and executes the composite action on contact. Behavior is pre-warmed at spawn time; state changes trigger re-evaluation via `state_changed` WS message. See [cache.md](cache.md) for the cache design.

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
