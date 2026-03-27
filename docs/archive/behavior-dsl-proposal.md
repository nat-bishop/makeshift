# Behavior DSL: Bridging LLM Creativity to Game Engine

## The Problem

The game's creation pipeline: player types a description → LLM generates structured output → Flux generates a sprite → object enters the game world.

The LLM understands what a "frozen vortex that launches enemies" does. Flux draws it perfectly. But the game engine receives `[FROZEN, COLD, WIND_SOURCE]` — three booleans from a vocabulary of 33. The vortex doesn't vortex. It doesn't launch anything. It sits on the ground, cold and windy, because the tag system can only express *what things are*, not *what things do*.

**Tags are a lossy compression layer.** The LLM's understanding of object behavior is destroyed at the tag boundary. A cannon doesn't shoot, a cop doesn't patrol, a vortex doesn't pull. Everything becomes a physics prop with categorical properties. The 55 hand-authored rules (tag × tag → effect) cover basic material interactions (fire burns wood, electricity conducts through metal) but can't express per-object behaviors, temporal sequences, area effects, or any action the player imagines that doesn't decompose into two objects colliding.

**What's lost:**
- Actions: "shoots," "chases," "orbits," "grows," "teleports"
- Targeting: "seeks enemies," "attracts metal," "follows the player"
- Temporal sequences: "launches upward, then pulls back after 2 seconds"
- Area effects: "everything in radius gets pulled in"
- Self-modification: "gets stronger each time it kills something"
- Conditional logic: "explodes when health drops below 50%"

The tag system handles material/physical classification well. It doesn't need to be replaced for that purpose. What's missing is a complementary system for *behavior* — a way for the LLM to tell the engine what an object *does*, not just what it *is*.

---

## The Solution: A Behavior DSL

A **Domain-Specific Language** — a small, constrained instruction set that the LLM generates and the game engine executes. The LLM produces a behavior specification alongside tags, and a BehaviorExecutor on the Godot side interprets it.

The DSL is **declarative, not imperative**. It describes what should happen using a fixed vocabulary of triggers and actions with bounded parameters. It can't express arbitrary computation, infinite loops, or unsafe operations. It's closer to filling out a form than writing code.

**Creation flow changes from:**
```
Player: "frozen vortex that launches enemies"
  → LLM: tags=[FROZEN, COLD, WIND_SOURCE]
  → Engine: cold windy object (sits there)
```

**To:**
```
Player: "frozen vortex that launches enemies"
  → LLM: tags=[FROZEN, COLD] + behaviors=[
      always: FORCE all_nearby toward_self strength=400 rotational=200
      always: MODIFY all_nearby(radius=200) temperature -20/sec
      on_contact(living): FORCE target up strength=600
                          WAIT 1.5s
                          FORCE target toward_self strength=800 duration=2s
    ]
  → Engine: spinning attraction field, freezes surroundings,
            launches living things up then yanks them back
```

The tag system stays for material classification and physical rules. The DSL adds behavioral expressiveness on top. This matches how Scribblenauts structured its object system (see below).

---

## DSL Primitives

The DSL needs a small number of atomic operations that compose into complex behaviors. These map directly to existing Godot engine capabilities:

**Triggers** (when something happens):
| Trigger | Engine mapping |
|---------|---------------|
| `always` | `_physics_process()` — runs every frame |
| `on_contact` | `body_entered` signal |
| `on_timer(interval)` | `Timer` node |
| `on_proximity(radius)` | `Area2D` with `CircleShape2D` |
| `on_create` | `_ready()` |
| `on_destroy` | `tree_exiting` signal |
| `on_use` | Player input while equipped |

**Actions** (what happens):
| Action | Engine mapping |
|--------|---------------|
| `force(target, direction, strength)` | `apply_central_impulse()` / `apply_force()` |
| `damage(target, amount)` | `take_damage()` method |
| `spawn(description, position, velocity)` | Object creation pipeline |
| `modify(target, property, value)` | Property setter |
| `move(direction, speed)` | Steering behavior / velocity |
| `connect(target, type)` | `PinJoint2D` / `DampedSpringJoint2D` |
| `wait(seconds)` | `await create_timer().timeout` |
| `destroy(target)` | `queue_free()` |

**Targets** (who gets affected):
| Target | Meaning |
|--------|---------|
| `self` | This object |
| `contact_body` | The thing that triggered the contact |
| `all_nearby(radius)` | Everything within radius |
| `nearest(filter)` | Closest matching object |

**Safety bounds:** Forces clamped to ±1000. Radii clamped to 50–600. Spawn rate limited (max 1/sec). Sequence length capped (max 5 actions per trigger). No recursion. No arbitrary code execution.

---

## How It Works in Practice

The LLM generates a `behaviors` list as part of `CreatorOutput`, validated by Pydantic on the backend, sent as JSON to the Godot client, and interpreted by a `BehaviorExecutor` component attached to each object.

**Backend:** Behavior schema defined as Pydantic models. LLM system prompt includes the trigger/action vocabulary with examples. Validators enforce parameter bounds and sequence length limits.

**Godot:** `BehaviorExecutor` is a ~200-line interpreter. On `_ready()`, it reads the behavior spec from the blueprint dictionary. For each behavior: sets up the trigger mechanism (timer, area, signal connection), and when triggered, walks the action list calling the corresponding engine APIs.

Most objects have zero behaviors — a rock, a plank, a wall. These remain tag-only physics props. Behaviors are for objects where the LLM recognizes the description implies action: creatures, weapons, traps, machines, magical effects.

---

## Precedent Systems

### Scribblenauts (Objectnaut engine, 2009–2013)

Scribblenauts used **three complementary layers**, not one:

1. **Properties tab** — static physical characteristics: weight, buoyancy, fire state, electrical properties. Equivalent to our tag system. Defined *what an object is*.

2. **Behaviors tab** — category-level AI reactions using seven verbs: Destroy, Eat, Investigate, Follow, Protect, Use, Ride. Each verb targeted object categories (e.g., "Lion Destroys category Prey"). Defined *how living objects react to categories of other objects*. No equivalent in our system.

3. **Scripting tab** — trigger → action DSL for custom event-driven logic. Triggers: "is created," "is destroyed," "gets eaten," "is used while equipped." Actions: create object, destroy object, apply adjective. Hard limits: max 3 actions per trigger, max 3-second wait.

**The scripting tab was complementary to the other two systems, not a replacement.** Properties handled physics. Behaviors handled category AI. Scripting handled everything the other two couldn't express — event-driven custom logic like "when created, apply the adjective 'burning' to self" or "when eaten, spawn an explosion." Our DSL proposal fills the same role: complementary to tags, not replacing them.

### Warcraft 3 Trigger Editor (Blizzard, 2002)

EVENT → CONDITION → ACTION architecture. ~18 event categories, ~25 condition types, ~300 atomic actions across 25 categories (AI, Camera, Unit, Player, Environment, etc.). Supported control flow (if/then/else, for-each, wait). Everything composed via dropdown menus — no code required for basic use.

Two tiers: the visual trigger editor (DSL) for accessible composition, and JASS (full scripting language) underneath for advanced modders. Every visual trigger compiled down to JASS. This two-tier approach enabled DotA — modders composed "dummy abilities" (presentation) with triggers (custom mechanics) to create spell behaviors impossible in the base ability system.

**Relevance:** Demonstrates that a constrained DSL can produce enormous behavioral variety from a fixed action vocabulary, and that the visual/declarative layer should compile down to something the engine natively executes.

### Noita (Nolla Games, 2019)

Entity behavior defined through **component composition in XML**. The `AnimalAIComponent` defines creature behavior via 21 enumerated states (Wandering, AttackingMelee, AttackingRanged, Escaping, Eating, Investigating, etc.) with numeric parameters: detection range, aggression probability, melee damage, projectile entity, dash distance, flee threshold.

Wand spells compose through a **deck/hand/discard card metaphor**. Modifiers don't modify other spells — they modify a "shot state" (accumulated damage, spread, cast delay). Projectiles carry the accumulated state. Multicasts draw multiple spells into one shot state. Triggers/timers create nested shot states.

**Relevance:** Noita's power comes from composing a small set of well-defined primitives (21 AI states, ~200 spell effects) with numeric parameters, not from unlimited scripting. The behavior vocabulary is finite and bounded; the composition is what creates emergence.

### GROMIT (UC Berkeley, 2024)

The closest existing system to LLM-generated game behavior. Uses GPT-4 to generate C# MonoBehaviour scripts at runtime in Unity. Converts the game scene to a JSON "Scene State Graph" so the LLM can reason about spatial relationships. Has a compilation-error feedback loop: if generated code fails to compile, the error is sent back to GPT-4 for correction.

**Relevance:** Proves that LLMs can generate game object behaviors from natural language in a live game engine. However, GROMIT generates *arbitrary C# code* — maximum flexibility, minimal safety. Our DSL approach trades some flexibility for safety by constraining the LLM to a fixed action vocabulary rather than arbitrary code generation.

### Voyager (NVIDIA, 2023)

LLM-powered Minecraft agent that generates JavaScript programs (using Mineflayer APIs) for in-game actions. Maintains a **skill library** indexed by text embeddings — when facing a new task, retrieves semantically similar past skills as context. Skills compose: complex skills call simpler skills. Iterative refinement loop: generate code → execute → check result → retry if failed.

**Relevance:** Demonstrates LLM-generated behavior code with a skill library for reuse. The embedding-indexed skill retrieval is directly applicable — cached behavior patterns for common object types ("sword behaviors," "creature behaviors") could be retrieved and adapted rather than generated from scratch each time.

---

## Relationship to Tags

Tags and the behavior DSL serve different purposes and coexist:

| Aspect | Tags | Behavior DSL |
|--------|------|-------------|
| Describes | What an object IS | What an object DOES |
| Examples | FROZEN, SHARP, HEAVY | Force field, seek target, launch on contact |
| Interaction model | Collision between two tagged objects | Autonomous actions, area effects, temporal sequences |
| Rule source | 55 hand-authored rules | LLM-generated per object |
| Determinism | Same tags → same rules (deterministic) | LLM-generated (validate for consistency) |
| Scope | Material/physical classification | Behavioral/dynamic effects |

Tags remain the source of truth for: material interactions (fire/ice/electricity), physics properties (mass, friction, buoyancy), equipment slot mapping, and the tag budget/balance system.

The DSL handles: autonomous movement, area effects, projectile spawning, temporal sequences, conditional logic, self-modification, and any behavior the player describes that isn't a material property.

Some current tag behaviors could migrate to DSL over time. `HEAT_SOURCE` as a tag could become a behavior: `always: MODIFY all_nearby(radius=50) temperature +30/sec`. But this migration is optional — both systems operate simultaneously.

---

## Open Questions

1. **LLM reliability:** Can the LLM consistently generate valid behavior specs? The tag system works because it's 33 options with budget validation. The DSL is more expressive — more ways to generate something incoherent. Mitigation: strong examples in system prompt, Pydantic validation, parameter clamping, cached behavior templates for common object types.

2. **Spawn economics:** When a behavior spawns an object ("cannon shoots cow"), does the spawned object cost session budget? If yes, behavioral items drain budget fast. If no, infinite free objects. Possible: spawned objects use a cached blueprint (free if previously created) or cost reduced budget.

3. **Performance:** `always` triggers run every physics frame. An object with `FORCE all_nearby(radius=300)` queries for neighbors every frame. Bounded by clamped radius and a per-object behavior count limit, but dense scenes with many behavioral objects could be expensive.

4. **Visual feedback:** The DSL describes mechanics, not visuals. A "force toward_self" is invisible without a particle effect or animation. The LLM could also specify visual hints (`visual: spiral_particles, color: ice_blue`) or the engine could infer them from action types.

5. **Scope boundary:** Where does the DSL stop and "you need a real scripting language" begin? Warcraft 3 answered this with two tiers (visual triggers + JASS). We may eventually need a similar escape hatch for complex behaviors the DSL can't express.
