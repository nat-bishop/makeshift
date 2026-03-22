# Game Design

## Core Concept

"Scribblenauts meets Terraria" — a 2D physics sandbox where players type text descriptions to create game objects. An LLM (Gemini) interprets descriptions into tagged blueprints with visual descriptors. A generative model (Flux) produces pixel art sprites. Objects interact through a tag-based rule system, enabling emergent puzzle-solving: fire melts ice, water extinguishes fire, electricity propagates through conductors.

Player creativity is constrained by the tag budget system — every object has a power budget of 10, and tags cost 1-5 points. This creates meaningful choices: a fire sword (SOLID+RIGID+SHARP+HEAT_SOURCE+TOOL = 9) leaves little room for extras, while a simple wooden plank (SOLID+RIGID+FLAMMABLE+BREAKABLE+CLIMBABLE = 6) is cheap and versatile.

## Tag System

33 tags across 8 categories. Tags are the atomic unit of the entire game — they drive physics, interactions, equipment effects, durability, and visual placeholders.

### Categories and Cost Curve

| Category | Tags | Cost range |
|----------|------|------------|
| Physical State | SOLID, LIQUID, GAS, RIGID, FLEXIBLE, HEAVY, LIGHT | 1-2 |
| Temperature | FROZEN, COLD, HOT, MOLTEN | 2-4 |
| Energy | FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE | 1-5 |
| Surface | SHARP, STICKY, SLIPPERY, REFLECTIVE | 2 |
| Mechanical | BOUNCY, CLIMBABLE, BREAKABLE | 1-2 |
| Interaction | WEARABLE, TOOL | 2 |
| Environmental | FLOATING, WIND_SOURCE, CORROSIVE, TOXIC | 2-4 |
| Special | LIVING, GLOWING, CONDUCTING, INSULATING | 2-3 |

**Design rationale**: Passive/physical properties are cheap (cost 1) because they describe what an object *is*. Active/energy properties are expensive (cost 3-5) because they describe what an object *does* — and doing things creates interactions, which create gameplay.

EXPLOSIVE (cost 5) is the most expensive because it's the most powerful single-tag effect: area damage on heat or electricity contact.

### Contradiction Pairs (12)

Tags that can't coexist on the same object:

```
FROZEN↔MOLTEN    FROZEN↔HOT     COLD↔HOT      COLD↔MOLTEN
HEAVY↔LIGHT      LIQUID↔RIGID   GAS↔RIGID     GAS↔HEAVY
SOLID↔LIQUID     SOLID↔GAS      LIQUID↔GAS    STICKY↔SLIPPERY
```

Enforced by Pydantic validators on `CreatorOutput`. Violations trigger `ModelRetry` with feedback to the LLM, not hard failures.

### Transferable Tags (14)

Tags that transfer from equipped items to the player's effective tag set:

HEAT_SOURCE, COLD, SHARP, ELECTRIC, MAGNETIC, WIND_SOURCE, CORROSIVE, TOXIC, FLOATING, GLOWING, REFLECTIVE, INSULATING, CONDUCTING, STICKY

This is what makes equipment meaningful — equipping a fire sword gives the player HEAT_SOURCE and SHARP, so touching a flammable object ignites it.

## Rule System

~55 `InteractionRule` definitions in `engine/rules_data.py`. Each rule specifies:
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
| Electricity | ELECTRIC + CONDUCTING → electrify + propagate, ELECTRIC + LIQUID → electrify | Yes (propagate) |
| Physical | SHARP + BREAKABLE → damage, HEAVY + BREAKABLE → damage, BOUNCY + anything → force | No |
| Counter | INSULATING blocks ELECTRIC, REFLECTIVE reflects HEAT_SOURCE | No |
| Magnetic | MAGNETIC + CONDUCTING → attract force | No |
| Environmental | WIND_SOURCE + LIGHT → push, CORROSIVE + BREAKABLE → corrode, TOXIC + LIVING → damage | No |

### Wildcard Rules

Rules with empty `tags_required_b` match any second object. Used for unconditional effects: STICKY + anything creates adhesion, CLIMBABLE + player enables climbing.

## Object Economy

| Metric | Value |
|--------|-------|
| Cost per object | $0.041 (LLM ~$0.001 + image ~$0.04) |
| Session budget | $1.00 (default, configurable) |
| Max objects per session | ~24 |
| Seed objects provided free | 15 |
| Tag budget per object | 10 |
| Tags per object | 2-6 (enforced by LLM validator) |
| Name length | 1-3 words (enforced by LLM validator) |

### Seed Objects (15)

Each session starts with a curated set covering diverse tag combinations:

| Object | Key Tags | Gameplay Role |
|--------|----------|---------------|
| Wooden Plank | SOLID, RIGID, FLAMMABLE, CLIMBABLE | Bridges, ladders, fuel |
| Rope | FLEXIBLE, FLAMMABLE, CLIMBABLE, LIGHT | Climbing, wind-affected |
| Boulder | HEAVY, BREAKABLE | Crushing, blocking |
| Torch | HEAT_SOURCE, HOT, GLOWING | Ignition source, light |
| Bucket of Water | LIQUID, HEAVY | Extinguishing, freezing |
| Trampoline | FLEXIBLE, BOUNCY, BREAKABLE | Vertical traversal |
| Ladder | RIGID, CLIMBABLE, FLAMMABLE | Climbing |
| Shield | HEAVY, REFLECTIVE, WEARABLE | Defense, heat reflection |
| Sword | RIGID, SHARP, TOOL | Damage, equippable |
| Ice Block | FROZEN, COLD, SLIPPERY, BREAKABLE | Freezing, melting |
| Fan | WIND_SOURCE, LIGHT, TOOL | Wind, push light objects |
| Balloon | GAS, LIGHT, FLOATING, BREAKABLE | Floating platforms |
| Metal Plate | HEAVY, CONDUCTING, MAGNETIC | Electricity, magnetism |
| TNT | EXPLOSIVE, FLAMMABLE, BREAKABLE | Area destruction |
| Umbrella | FLEXIBLE, WEARABLE, WIND_SOURCE | Equipment + wind |

## Equipment System

3 slots: **hand**, **back**, **head**. Only objects with WEARABLE or TOOL tags are equippable.

### Slot Assignment

`EQUIP_SLOT_MAP` in `models/tags.py` maps `base_form → slot`:
- **Hand**: sword, axe, hammer, wand, tool, wrench, torch, fan
- **Back**: shield, jetpack, cape, wings
- **Head**: helmet, crown, goggles
- **Default**: hand (if base_form not in map)

### Equipment Effects

Equipped items transfer their transferable tags to the player. The player always has the LIVING tag. `get_effective_tags()` merges LIVING + all equipped items' transferable tags.

**Physics modifiers** (checked in `player.gd._physics_process`):
- FLOATING → gravity ×0.3
- HEAVY → speed ×0.7

## Durability & Damage

Starting durability depends on tags:

| Tag | Durability |
|-----|-----------|
| BREAKABLE | 50 |
| RIGID | 200 |
| FLEXIBLE | 100 |
| Default (none of above) | 150 |

Priority: BREAKABLE checked first, then RIGID, then FLEXIBLE, then default.

**Damage-over-time (DOT)**:
- IGNITE: 10 damage per second for 5 seconds (50 total)
- CORRODE: 15 damage per second for 3 seconds (45 total)

Objects reaching 0 durability are destroyed (`queue_free()`).

## Levels

3 puzzle levels using the `BaseLevel` pattern (extends Node2D). Each level has a spawn point, goal area, and objective text. Levels are designed to be solvable multiple ways — a gap can be bridged with a plank, crossed with a floating balloon, or bypassed by climbing.

Player progression tracked via `current_level` and `levels_completed` in session state, synced to backend.
