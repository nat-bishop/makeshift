# Object System V2 — Design Brief

## The Problem

Makeshift is a Scribblenauts-inspired 2D sandbox where players type descriptions and an LLM creates game objects. The current system has the LLM pick from 27 boolean tags (FLAMMABLE, SHARP, HEAVY, etc.) and optionally write one behavior in a DSL (`ON_CONTACT → MOVE_TOWARD → NEAREST_LIVING`). 59 hand-authored rules define what happens when tag pairs interact (fire + flammable = ignite). The LLM achieves ~82% tag recall and struggles with behavior notation — we simplified from 2-4 behaviors to 0-1 because accuracy was too low.

The fundamental limitations:

1. **Too few engine verbs.** The game can only do 10 things: damage, heal, push, slow, add/remove tag, move toward/away, spawn projectile, explode, self-destruct. There's no attach, contain, consume, ride, climb, or hold. A rope swing, grappling hook, bucket of water, or mountable horse can't exist regardless of tagging.

2. **Tags are boolean, not parameterized.** A rusty dagger and an enchanted greatsword both get SHARP and deal identical damage. Scribblenauts had numeric properties — weapon damage 0-100, health 0-1500, weight as a continuous value. Our tags flatten everything to on/off.

3. **Behaviors lack targeted intent.** A hostile wolf chases "nearest living thing" — it can't distinguish prey from threats from irrelevant creatures. Scribblenauts had 9 behavior verbs (destroy, eat, investigate, follow, protect, use, ride, steal, flee) that each targeted specific CATEGORIES of objects. "Lion: eat → Food, destroy → Small Animal, flee → Fire." One rule covered thousands of objects through category membership.

4. **The LLM is doing the wrong job.** It's picking mechanical tags (LIGHT means "wind-pushable", not "lightweight") instead of describing objects in terms it naturally understands. The system prompt is ~200 lines of mechanical explanations. The LLM should describe objects in intuitive terms, and the engine should derive mechanics.

## The Proposed Solution

A single LLM call outputs structured, intuitive fields. The engine resolves mechanics from those fields. No behavior DSL. No direct tag selection.

### LLM Output Schema

```json
{
  "name": "Grappling Hook",
  "substance": "metal",
  "properties": ["sharp", "light"],
  "element": null,
  "interaction": ["holdable", "throwable"],
  "capabilities": ["attach_on_contact", "pull_holder"],
  "behaviors": [
    {"verb": "eat", "target": "food, especially donuts"},
    {"verb": "destroy", "target": "hostile criminals"},
    {"verb": "flee", "target": "supernatural monsters"}
  ],
  "visual": {"description": "iron hook on coiled rope", "size": "small"}
}
```

**Substance** (pick 1 from ~16) — what it's made of. Metal, wood, stone, glass, rubber, ice, flesh, fiber, water, oil, slime, lava, fire, smoke, lightning, plant. Each maps to base traits AND a numeric property profile (mass, durability, friction, conductivity, burn_rate). This replaces both tag selection for physical properties AND the hardcoded TagPhysicsMap.

**Properties** (pick 0-2 from ~10) — notable physical modifiers beyond what the substance implies. Sharp, heavy, light, bouncy, breakable, sticky, reflective, insulating, explosive, flying. These override or extend substance defaults.

**Element** (pick 0-1 from ~8) — energy the object produces. Burning, electric, magnetic, freezing, acidic, toxic, explosive, windy. Orthogonal to substance — a metal sword (substance) can carry fire (element).

**Interaction** (pick 0-2 from ~7) — how players/creatures physically interact with it. Holdable, throwable, climbable, rideable, edible, wearable, containing. Each maps to a pre-built Godot component that enables that player interaction. These are NEW engine features that don't exist yet.

**Capabilities** (pick 0-2 from ~15) — special engine mechanics for objects that need more than their traits provide. Attach_on_contact, pull_holder, heal_field, timed_explosion, returns_to_source, apply_trait_on_contact, guard_area, attract_trait, absorb_projectiles, grow, emit_substance, friendly_to_player, etc. Each is a pre-built Godot component. Most objects need zero capabilities — substance + properties + element + interaction handles 70-80% of objects.

**Behaviors** (0-4 verb+target pairs) — autonomous AI using Scribblenauts' 9 verbs. Destroy, eat, investigate, follow, protect, use, ride, steal, flee. Target is freeform natural language describing WHAT the object targets for that verb.

### Embedding-Based Behavior Targeting

The key innovation for behavior targeting: at creation time, each behavior's target string is embedded into a vector. Each object's identity (name + substance + key traits) is also embedded. At runtime, when objects encounter each other, dot products between behavior target vectors and object identity vectors determine whether a behavior activates.

Cop's eat target: embed("food, especially donuts and pastries") → vector
Donut's identity: embed("donut — sweet glazed pastry") → vector
Runtime: dot product = 0.91 → cop eats donut.

Vegetarian's eat target: embed("vegetables, fruits, plant-based food") → vector
Hamburger's identity: embed("hamburger — beef patty in bun") → vector
Runtime: dot product = 0.35 → vegetarian ignores hamburger.

This happens with a local embedding model (~5ms per embedding on GPU at creation time). Runtime comparison is microsecond dot products. No LLM calls during gameplay. Cultural knowledge (cops love donuts, vegetarians don't eat meat) is captured in the embedding space.

Novel objects work automatically — a "glazed kruller" that nobody authored matches "food, especially donuts" through embedding similarity. This is how the system beats Scribblenauts' hand-authored dictionary.

### What Stays, What Changes

**KEEP: The rule/cascade system.** Tag-pair rules (HEAT_SOURCE + FLAMMABLE → ignite) with cascade chains are the strongest part of the current engine. Physical interactions stay data-driven and composable. But rule effects become parameterized by substance profiles instead of hardcoded values — a campfire and a volcano both have heat_source trait but deal different damage based on their substance's heat_output value.

**KEEP: The tag/trait concept.** Internally, objects still have traits (the current tags). The difference is the LLM doesn't pick traits directly — they're derived from substance + properties + element. The rule system matches on traits just as before.

**REPLACE: BehaviorExecutor → CapabilityManager.** The current trigger→action→target behavior system is replaced by capability components (self-contained Godot nodes) and Scribblenauts-style verb behaviors with embedding-targeted matching. Each capability is a pre-built Godot component that handles its own state machine.

**REPLACE: TagPhysicsMap → SubstanceProfiles.** Physics properties (mass, gravity, friction, bounce) come from substance profiles with continuous values, not from boolean tag lookups. This enables "a rusty dagger" and "an enchanted greatsword" to feel mechanically different.

**ADD: Player interaction components.** Holdable, throwable, climbable, rideable, wearable, edible, containing — these are new Godot features. Each is a focused implementation (~1-2 weeks each). They're the biggest gap between Makeshift and Scribblenauts.

**ADD: New engine verbs.** Attach (physics joints), consume (destroy + gain benefit), contain (hold + release), mount (player rides), climb (player traverses surface), transform (replace object). These expand the 10 current engine verbs to ~17, enabling objects like rope swings, grappling hooks, rideable mounts, and containers.

### Grouped LLM Selection

The groups are designed so each one is a genuinely separate decision with a small option set. The LLM picks from 6 small menus instead of one large one. Each group uses intuitive words ("burning" not "HEAT_SOURCE"), and the backend maps to internal trait names. This should improve on the current 82% accuracy because the new terms are self-documenting — CLIMBABLE means exactly what it says, unlike LIGHT which currently means "wind-pushable."

## Scribblenauts Reference

Scribblenauts (2009-2013) shipped with ~22,000 objects on a custom engine called Objectnaut. Key architecture decisions worth studying:

- **10 property tabs** with ~40-50 structured fields (not boolean tags) — numeric damage, health, weight, speed, movement modes, container sizes, equipment slots
- **9 behavior verbs** targeting **categories** of objects, not individuals — "Lion: Eat → Food" covered thousands of objects
- **"Objects React To It As"** — an identity override field that decoupled name from behavioral archetype (a "zombie firefighter" reacts as Zombie)
- **Two-tier category hierarchy** — objects belonged to multiple categories simultaneously (Apple = Food + Fruit + Classroom)
- **80% of dev time was hand-authored exceptions** — the system couldn't handle cultural nuances (cop+donut, vegetarian+hamburger) without per-object overrides

The full research is in `docs/scribblenauts-deep-dive.md`. The action plan items most relevant are #14 (prototype library), #15 (archetype field), #16 (behavior verbs), #18 (numeric properties), #22 (category tags).

## Key Design Questions for the Implementer

1. **Substance list**: What are the right ~16 substances, and what numeric profiles should each have? Need to cover solids, liquids, gases, energy, and edge cases (lava, slime, lightning).

2. **Capability list**: What are the right ~15 capabilities? Each one is a Godot component to build. Prioritize by gameplay impact vs implementation cost.

3. **Behavior verb list**: Scribblenauts had 9. Do we need all 9? Are there verbs they missed? How do verbs map to engine actions?

4. **Embedding model choice**: Which local embedding model gives the best food/non-food, threat/non-threat separation for behavior targeting? Needs benchmarking.

5. **Rule parameterization**: How do substance profiles feed into rule effects? What numeric fields does each substance need?

6. **Migration path**: How to evolve from the current system incrementally — what can be built and tested independently?

7. **Eval adaptation**: The current eval suite has 90 cases measuring tag recall. How should evals change to measure the new system's quality?
