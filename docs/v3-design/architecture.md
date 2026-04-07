# V3 Architecture

## What this actually is

V2 with fewer enums, LLM-generated physics, and auto-populated interaction rules instead of hand-authored ones.

The pitch isn't "delete everything and just ask the LLM." It's: **automate the most tedious part (rule authoring) while keeping the engine infrastructure that makes the game work.**

The architecture keeps: a state system (smaller), behavior verbs (same), affordances (simpler), contradiction resolution, and cascade control. What it replaces: substance profiles with LLM-generated numbers, hand-authored rules with an LLM-populated cache, tag derivation with interaction-only states, and the single complex creator call with a graph of tiny parallel calls.

See [local-llm-rules.md](local-llm-rules.md) for inference constraints. Key numbers:
- ~55ms base cost per call, input tokens are free
- ~7ms per output token — use numbered choices, not words
- Up to 8 parallel calls ≈ cost of 1 call
- 32 concurrent calls before GPU saturation

---

## Two interaction systems

This is the key architectural idea. The same two objects can produce different outcomes depending on HOW they meet.

### Passive interactions — "what happens when objects collide"

Physics-driven. Object A bumps into object B. Nobody intended it. The engine resolves it from the cached LLM evaluation.

**Examples:**
- Fire sword falls onto wooden shield → damage 40, add state on_fire
- Rock rolls into glass bottle → damage 60, destroy bottle
- Water splashes onto campfire → remove on_fire state, destroy water

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

When a new object enters the scene, evaluate it against every existing object:

```
Per pair, 5 parallel calls (1 token each, ~60ms):
- Damage to A? 0-100
- Damage to B? 0-100
- State change? 0-12 (from closed state list)
- Force? 0-100, 0=push/1=pull
- Mode? 0=instant, 1=continuous
```

Include both objects' physics properties in the prompt (input is free):
```
"[fire sword: 2kg, toughness 90, emits heat] hits 
 [wooden shield: 3kg, armor 20, hp 40]. Damage to B? 0-100"
```

The physics properties act as calibration anchors — the LLM sees toughness 40 and produces consistent damage across similar targets.

### State-based interaction table

States are a closed set of 7. The effect of being `on_fire` on nearby objects is categorical — fire burns wood regardless of whether a wall or a sword is on fire. This means state interactions can be pre-computed at spawn time per object × per state, not per pair:

```
Per object × 7 states (1 call each, 1 token, ~60ms per batch):
"An on_fire object is near [wooden chair: 1kg, armor 20, hp 30]. 
 Damage? 0-100"  → 20
"State change? 0-7" → 1 (on_fire — fire spreads)
"Mode? 0=instant 1=continuous" → 1
```

This is O(N) per state, not O(N²). When the wall catches fire, the engine looks up "on_fire + wooden chair" from this pre-computed table — no runtime LLM call, no cache invalidation. The state interaction table provides the same categorical generalization that V2's tag rules provided (HEAT_SOURCE + FLAMMABLE → ignite), just auto-generated.

### Pairwise cache invalidation

The pairwise cache (object A hits object B) is for BASE interactions between objects without states. When an object gains a state, its state-based interactions are handled by the state interaction table above — not by invalidating and re-evaluating the pairwise cache. The pairwise cache stays valid because it describes what happens when the objects collide in their base form.

---

## Creation cache

Separate from the interaction cache. Maps object names to their creation-time LLM answers (physics, affordance, destructibility, field, autonomous, behaviors).

First "fire sword" → mass 2.0, affordance carry, etc. All subsequent "fire sword" creations return the same values. This is a correctness requirement, not optimization — two identical objects should have identical physics. Without this, players can't predict what they're creating.

Exact name match only. "Fire sword" and "big fire sword" are different cache entries — they're different objects.

---

## Creature movement — direct pairwise evaluation

Replaces seek/avoid lists and semantic target matching from V2.

When an autonomous creature spawns, evaluate its movement reaction to every object in the scene:

```
Per creature × object (1 call, 2 tokens):
"Zombie cop sees donut. 
 0=approach 1=flee 2=orbit 3=ignore. Strength 0-100?"
→ 0, 90 (approach, strongly)
```

No freeform target strings. No "is glazed pastry a match for donuts?" semantic matching. Just direct pairwise: does THIS creature care about THIS specific object?

**Why this replaces seek/avoid:** V2 used freeform target strings ("donuts +90") then matched each scene object against them. This had vocabulary drift problems — the same issues that killed embeddings for targeting. Direct pairwise evaluation is cheaper (fewer calls), more accurate (no matching layer), and doesn't drift.

When a new object spawns, evaluate it against all existing creatures' movement reactions. When an object changes state, re-evaluate affected creature reactions (lazy, same as passive cache).

---

## Cascade control

State changes from interactions can cascade (fire spreads to nearby wood). Same controls as V2:

- **Depth limit:** max 3 levels of cascade
- **Dedup:** pair key `(id_a, id_b)` can't fire twice in one cascade chain
- **No recursive triggers:** state changes from cascaded interactions don't trigger further cascades
- **Field rate limit:** field effects tick every 2s, not every frame
- **State contradictions:** adding on_fire removes frozen and wet automatically (engine-enforced, see [engine-primitives.md](engine-primitives.md))

---

## What's genuinely new vs V2

1. **LLM-populated interaction cache** — replaces 56 hand-authored rules with unlimited auto-generated pairs. Cop+donut, vampire+garlic, mongoose+cobra all work without anyone coding them.

2. **LLM-generated physics** — a "fiery ice sword" gets reasonable mass/bounce/friction without substance mixing. A "thought bubble" gets mass 0.001 and floats.

3. **Graph-based creator** — parallel 1-token calls instead of 1 complex call. Faster, more reliable, works on smaller models.

4. **Direct pairwise movement** — "zombie cop sees donut → approach 90" evaluated directly, no intermediate matching layer.

5. **State-based interaction table** — categorical state effects (fire burns wood) pre-computed at spawn. No runtime LLM calls for state cascades.

6. **No creator-assigned tags** — objects are born stateless. All states come from interactions.
