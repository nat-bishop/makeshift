# Game Design

## Core Concept

"Scribblenauts meets Terraria" — a 2D physics sandbox where players type text descriptions to create game objects. An LLM (Gemini) interprets descriptions into tagged blueprints with visual descriptors and autonomous behaviors. Gemini image generation produces sprites. Objects interact through a tag-based rule system and behavior system, enabling emergent puzzle-solving: fire melts ice, a dragon patrols and breathes fire, a time bomb explodes after a delay.

Player creativity is constrained by two budget systems — every object has a tag budget of 10 and a behavior budget of 6. Tags define what an object *is*; behaviors define what it *does*. Together they create meaningful design choices: a fire source (SOLID+RIGID+HEAT_SOURCE+HOT = 7 tag cost) leaves room for a MOVE_TOWARD behavior (cost 2), while adding EXPLODE on low health (cost 3) turns any object into a trap.

## Tag System

30 tags across 7 categories. Tags are the atomic unit of the entire game — they drive physics, interactions, and durability.

### Categories and Cost Curve

| Category | Tags | Cost range |
|----------|------|------------|
| Physical State | SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT | 1-2 |
| Temperature | FROZEN, COLD, HOT, MOLTEN | 1-4 |
| Energy | FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE | 1-5 |
| Surface | SHARP, STICKY, SLIPPERY, REFLECTIVE | 1-2 |
| Mechanical | BOUNCY, BREAKABLE | 1-2 |
| Environmental | FLOATING, WIND_SOURCE, CORROSIVE, TOXIC | 2-4 |
| Special | LIVING, GLOWING, CONDUCTING, INSULATING | 2-3 |

**Design rationale**: Passive/physical properties are cheap (cost 1) because they describe what an object *is*. Active/energy properties are expensive (cost 3-5) because they create interactions, which create gameplay.

EXPLOSIVE (cost 5) is the most expensive because it's the most powerful single-tag effect: area damage on heat or electricity contact. With the behavior system, a cheaper EXPLODE action (behavior budget) can achieve similar results with more control — but requires a trigger condition, while the tag fires automatically via the rule engine.

### Contradiction Pairs (14)

Tags that can't coexist on the same object:

```
FROZEN↔MOLTEN    FROZEN↔HOT     COLD↔HOT      COLD↔MOLTEN
HEAVY↔LIGHT      LIQUID↔RIGID   GAS↔RIGID     GAS↔HEAVY
SOLID↔LIQUID     SOLID↔GAS      LIQUID↔GAS    STICKY↔SLIPPERY
CONDUCTING↔INSULATING           REFLECTIVE↔STICKY
```

Enforced by Pydantic validators on `CreatorOutput`. Violations trigger `ModelRetry` with feedback to the LLM, not hard failures.

## Rule System

45 `InteractionRule` definitions in `engine/rules_data.py`. Each rule specifies:
- Required tags on object A and/or B
- Priority (higher fires first)
- Whether bidirectional (A↔B or only A→B)
- Whether cascade-eligible (can trigger chain reactions)
- Effects to apply

### Design Philosophy

**Intuitive**: Rules should match player intuition. Fire + flammable = ignite. Water + fire = extinguish. Sharp + breakable = damage.

**Chain reactions**: Cascade-eligible rules create emergent gameplay. Igniting one flammable object spreads HEAT_SOURCE to neighbors, which may ignite more flammable objects. Depth-limited to 3 to prevent infinite loops.

**Counters exist**: Every powerful interaction has a counter. INSULATING blocks ELECTRIC propagation. REFLECTIVE bounces HEAT_SOURCE. LIQUID extinguishes HEAT_SOURCE. This creates a rock-paper-scissors dynamic.

### Rule Categories

| Category | Example rules | Cascade? |
|----------|--------------|----------|
| Fire/Heat | HEAT_SOURCE + FLAMMABLE → ignite, + FROZEN → melt, + EXPLOSIVE → detonate | Yes (ignite) |
| Water/Cold | LIQUID + HEAT_SOURCE → extinguish, COLD + LIQUID → freeze | No |
| Electricity | ELECTRIC + CONDUCTING → electrify + propagate, ELECTRIC + LIQUID → electrify, ELECTRIC + FLAMMABLE → spark ignition, ELECTRIC + GAS → ionize plasma | Yes (conduction, spark, ionize) |
| Physical | SHARP + BREAKABLE → damage, HEAVY + BREAKABLE → damage, BOUNCY + anything → force | No |
| Counter | INSULATING blocks ELECTRIC, REFLECTIVE reflects HEAT_SOURCE | No |
| Magnetic | MAGNETIC + CONDUCTING → attract force | No |
| Environmental | WIND_SOURCE + LIGHT → push, CORROSIVE + BREAKABLE → corrode, TOXIC + LIVING → damage | No |

### Wildcard Rules

Rules with empty `tags_required_b` match any second object. Used for unconditional effects: STICKY + anything creates adhesion.

## Behavior System

Behaviors make objects autonomous. Tags define *what an object is*; behaviors define *what it does on its own*. The two systems are additive and independent — any object can have both, either, or neither.

### Design Philosophy

**Flat records, not behavior trees.** Each behavior is a single trigger→action→target record with optional condition and parameters. This is intentional: it keeps LLM output predictable, budget-checkable, and debuggable. Complex behavior (guard that retreats when hurt, then heals and re-engages) requires multiple behavior records, which is transparent and budget-constrained.

**Categorical parameters, not numeric.** Behaviors use named tiers (MINIMAL/LOW/MEDIUM/HIGH/EXTREME) rather than raw numbers. This lets the LLM describe intent ("intense fire") without guessing engine values, and lets the implementation tune those values without touching the data model.

**Separate budget from tags.** Behavior budget (6) is independent of tag budget (10). This prevents the LLM from having to make tag-vs-behavior tradeoffs in a single constrained budget — tags and behaviors serve different design roles and should be independently expressive.

### Vocabulary Summary

10 triggers: ALWAYS, ON_TIMER, ON_PROXIMITY, ON_CONTACT, ON_DAMAGED, ON_HEALTH_LOW, ON_TAG_ADDED, ON_CREATE, ON_DESTROY, ON_USE

12 actions: MOVE_TOWARD, MOVE_AWAY, PATROL, DEAL_DAMAGE, APPLY_FORCE, ATTRACT, SPAWN_PROJECTILE, EXPLODE, HEAL, ADD_TAGS, REMOVE_TAGS, SELF_DESTRUCT

5 targets: SELF, NEAREST_OBJECT, NEAREST_LIVING, NEAREST_PLAYER, CONTACT_BODY

3 condition types (free, no budget cost): HAS_TAG, NOT_HAS_TAG, TARGET_HAS_TAG

See [ARCHITECTURE.md](ARCHITECTURE.md) for implementation details (budget formula, numeric mappings, projectile system).

### Behavior Budget

| Action | Base cost |
|--------|-----------|
| SELF_DESTRUCT | 1 |
| MOVE_TOWARD, MOVE_AWAY, PATROL, DEAL_DAMAGE, APPLY_FORCE, ATTRACT, HEAL, ADD_TAGS, REMOVE_TAGS | 2 |
| SPAWN_PROJECTILE, EXPLODE | 3 (floor: 2) |

Intensity modifiers: MINIMAL -1, LOW/MEDIUM +0, HIGH +1, EXTREME +2. Budget per object: 6. Max behaviors: 3.

Conditions and messages are free — they add expressiveness without cost.

### Composing Tags and Behaviors

The tag and behavior systems interact through `ON_TAG_ADDED` triggers. This bridges the rule engine (which mutates tags on collision) to the behavior system:

- Rule engine adds HOT to a bomb → ON_TAG_ADDED(HOT) triggers EXPLODE
- Rule engine ignites an object → ON_TAG_ADDED(HEAT_SOURCE) triggers MOVE_AWAY from heat
- Behavior adds ELECTRIC tag → rule engine propagates it to CONDUCTING neighbors

This makes the two systems composable without tight coupling.

### Design Examples

**Dragon** (aggressor):
- Tags: LIVING, HEAT_SOURCE, HOT, HEAVY (cost 9)
- Behavior 1: ALWAYS → MOVE_TOWARD → NEAREST_LIVING, MEDIUM speed (cost 2)
- Behavior 2: ON_PROXIMITY(CLOSE) → SPAWN_PROJECTILE → NEAREST_LIVING, HIGH intensity, interval MEDIUM (cost 4)
- Total behavior cost: 6

**Time Bomb** (delayed threat):
- Tags: EXPLOSIVE, RIGID, BREAKABLE (cost 7)
- Behavior 1: ON_TIMER(ONCE_LONG) → EXPLODE → SELF, HIGH intensity (cost 4)
- Total behavior cost: 4

**Guard Dog** (reactive defender):
- Tags: LIVING, SHARP, RIGID (cost 4)
- Behavior 1: ALWAYS → PATROL → SELF, MEDIUM speed (cost 2)
- Behavior 2: ON_PROXIMITY(CLOSE) → MOVE_TOWARD → NEAREST_LIVING, FAST speed (cost 2)
- Behavior 3: ON_CONTACT → DEAL_DAMAGE → CONTACT_BODY, HIGH intensity (cost 3) — total 7 → too expensive; use MEDIUM (cost 2) instead
- Total behavior cost: 6

**Reactive Bomb** (tag-triggered via rule engine):
- Tags: EXPLOSIVE, FLAMMABLE, BREAKABLE (cost 7)
- Behavior 1: ON_TAG_ADDED(HOT) → EXPLODE → SELF, EXTREME intensity (cost 5)
- Total behavior cost: 5
- Note: The EXPLOSIVE tag would also fire via rule engine when HOT is added — for a reactive bomb that can detonate this way, omit EXPLOSIVE and rely purely on the behavior for greater control over timing and message.

## Player Controls

| Action | Input | Details |
|--------|-------|---------|
| Move | A/D or arrow keys | — |
| Jump | Space | — |
| Create object | Tab | Opens creation panel; pauses game while open |
| Kick | E | 0.5s cooldown |
| Debug overlay | F3 | Toggle |

**States**: IDLE, WALK, JUMP, FALL — driven by `is_on_floor()` and `velocity.y`.

### Push

Walking into any `RigidBody2D` applies a continuous impulse of **80 units** in the collision direction (`apply_central_impulse(push_dir * 80.0)`). No input required — contact is sufficient.

### Kick

Pressing E performs a rectangular shape query **48px wide × 32px tall** centered in front of the player. All `RigidBody2D` objects in range receive an impulse of **400 units** in the direction `(facing, -0.3).normalized()` — forward and slightly upward. 0.5s cooldown between kicks.

## Object Placement Workflow

After submitting a creation request:

1. `MaterializeEffect` plays at `player.position + (80, -32)` while the object is created and the sprite generates in the background.
2. When the HTTP response arrives, the game waits for the sprite. If the sprite is already cached (WebSocket beat HTTP), placement begins immediately.
3. Player enters placement mode — a semi-transparent ghost follows the mouse. If the sprite arrives while in placement mode, the ghost updates live.
4. Left-click to confirm placement; Escape to cancel. Placement spawns the object at the clicked world position.
5. If sprite generation fails entirely, placement proceeds without a sprite (ghost shows no texture).

During placement, the HUD hint changes to "Click: Place | Esc: Cancel".

## Debug Overlay

**F3** toggles debug mode. When active:

- Each object displays a floating label showing: `name [current_durability/max_durability]`, active tags (space-separated), and one line per behavior in `trigger > action` format.
- Labels update on durability change or tag count change (not every frame).
- HUD shows control hint bar: "Tab: Create | E: Kick | F3: Debug".

## Object Economy

| Metric | Value |
|--------|-------|
| Cost per object | $0.041 (LLM ~$0.001 + image ~$0.04) |
| Session budget | $1.00 (default, configurable) |
| Max objects per session | ~24 |
| Seed objects provided free | 15 |
| Tag budget per object | 10 |
| Behavior budget per object | 6 |
| Tags per object | 2-6 (enforced by LLM validator) |
| Behaviors per object | 0-3 (enforced by LLM validator) |
| Name length | 1-3 words (enforced by LLM validator) |

### Seed Objects (15)

Each session starts with a curated set covering diverse tag combinations:

| Object | Key Tags | Gameplay Role |
|--------|----------|---------------|
| Wooden Plank | SOLID, RIGID, FLAMMABLE | Bridges, fuel |
| Rope | FLEXIBLE, FLAMMABLE, LIGHT | Wind-affected fuel |
| Boulder | HEAVY, BREAKABLE | Crushing, blocking |
| Torch | HEAT_SOURCE, HOT, GLOWING | Ignition source, light |
| Bucket of Water | LIQUID, HEAVY | Extinguishing, freezing |
| Trampoline | FLEXIBLE, BOUNCY, BREAKABLE | Vertical traversal |
| Ladder | RIGID, FLAMMABLE | Flammable structure |
| Shield | HEAVY, REFLECTIVE | Defense, heat reflection |
| Sword | RIGID, SHARP | Damage |
| Ice Block | FROZEN, COLD, SLIPPERY, BREAKABLE | Freezing, melting |
| Fan | WIND_SOURCE, LIGHT | Wind, push light objects |
| Balloon | GAS, LIGHT, FLOATING, BREAKABLE | Floating platforms |
| Metal Plate | HEAVY, CONDUCTING, MAGNETIC | Electricity, magnetism |
| TNT | EXPLOSIVE, FLAMMABLE, BREAKABLE | Area destruction |
| Umbrella | FLEXIBLE, WIND_SOURCE | Wind interaction |

## Durability & Damage

Starting durability depends on tags:

| Tag | Durability |
|-----|-----------|
| BREAKABLE | 50 |
| RIGID | 200 |
| FLEXIBLE | 100 |
| Default (none of above) | 150 |

Priority: BREAKABLE checked first, then RIGID, then FLEXIBLE, then default.

**Damage-over-time (DOT)** — rule-defined; applied via DAMAGE effect with `tick_interval`/`tick_duration` fields:
- Ignition (HEAT_SOURCE + FLAMMABLE): 10 dmg/s for 5s (50 total)
- Spark ignition (ELECTRIC + FLAMMABLE): 8 dmg/s for 3s (24 total); also adds HEAT_SOURCE + HOT
- Corrosion (CORROSIVE + BREAKABLE): 15 dmg/s for 3s (45 total)

DOT does not stack — a new DOT on an already-burning object replaces the existing one.

Objects reaching 0 durability are destroyed (`queue_free()`).

## Levels

3 puzzle levels using the `BaseLevel` pattern (extends Node2D). Each level has a spawn point, goal area, and objective text. Levels are designed to be solvable multiple ways — a gap can be bridged with a plank, crossed with a floating balloon, or bypassed with a bouncy trampoline.
