# Level Design

Design patterns and BaseLevel API for Makeshift levels.

---

## Design Principles

1. **Every level requires creating objects** — the core mechanic must be exercised, not optional
2. **What the player creates matters** — a generic "wooden plank" should not be a universal solution; state properties (initial_states, susceptible_states) and durability must matter
3. **Seed objects demonstrate mechanics** — the player should observe state propagation and creature behavior before they create anything
4. **Multiple solution paths** — 3-4 approaches per level using different properties
5. **Hard to cheese** — the environment should punish thoughtless creation and reward deliberate choices
6. **Progressive complexity:** state interactions → creature behavior → combined
7. **Antagonistic objects are the differentiator** — Scribblenauts did tool-use puzzles; Makeshift should feature objects that fight back

---

## V3 Level Design Notes

The V3 interaction system replaces tag-based rules with:
- **State propagation**: objects with `initial_states` spread those states to nearby objects with matching `susceptible_states` every 2s
- **Essential-state destruction**: objects with `initial_states` are destroyed when all initial states are removed (fire extinguished = destroyed)
- **Collision force**: pairwise force (push/pull) is the only pairwise LLM result; all other interactions come from state spread
- **Creature behavior**: per-pair staged evaluation replaces fixed behavior verbs

Level puzzles should be designed around these mechanics. Examples:
- A fire (initial_states=[burning]) spreads to wood (susceptible_states=[burning]) → fire spread puzzle
- Ice (initial_states=[frozen]) — water extinguishes burning AND freezes susceptible objects
- Creating a wet object near electrified ones is dangerous (wet susceptible to electrified)
- Creatures with high priority toward specific states (firefighter → burning) create natural puzzles

**Seed object blueprints** should use the V3 `GameObjectBlueprint` format: no tags, no behavior verb lists, instead `initial_states`, `susceptible_states`, `autonomous`, `durability`, and `affordance`. See `CLAUDE.md` → Data Model Flow for the complete blueprint structure.

---

## BaseLevel API

All levels extend `BaseLevel`. Available helpers:

```gdscript
# Spawn a pre-defined game object from blueprint dict
_spawn_game_object(blueprint: Dictionary, pos: Vector2) -> Node

# Create a kill zone (999 dmg to objects, respawns player)
_create_kill_zone(pos: Vector2, size: Vector2) -> void
```

`BaseLevel` requires a `$Goal` Area2D node in the scene for level completion detection.

### V3 Seed Object Blueprint Format

```gdscript
# V3 blueprint — no tags, no behavior verbs
const FIRE_BLUEPRINT := {
    "id": "fire_01",
    "name": "Fire",
    "description": "a small campfire",
    "visual_description": "a small orange and yellow campfire with flickering flames",
    "physics": {
        "mass_kg": 0.1,
        "height_cm": 40,
        "surface": 0,      # 0=slippery 1=normal 2=sticky
        "bounce": 0,
        "gravity": 10,     # fire rises
    },
    "durability": 0,       # fragile (5 HP) — fire dies quickly when hit
    "affordance": 3,       # 3=nothing
    "autonomous": false,
    "speed": 2,
    "initial_states": [1], # spawns with burning (state 1)
    "susceptible_states": [],
    "destruction_result_name": "ash",
}

const WOOD_LOG_BLUEPRINT := {
    "id": "wood_01",
    "name": "Wood Log",
    "description": "a wooden log",
    "visual_description": "a brown cylindrical wooden log",
    "physics": {
        "mass_kg": 5.0,
        "height_cm": 60,
        "surface": 1,
        "bounce": 10,
        "gravity": 50,
    },
    "durability": 2,          # normal (40 HP)
    "affordance": 0,          # carry
    "autonomous": false,
    "speed": 2,
    "initial_states": [],
    "susceptible_states": [1], # catches fire (state 1)
    "destruction_result_name": "charred wood",
}
```

State IDs: 1=burning, 2=frozen, 3=wet, 4=electrified.

### GameManager Level Registration

```gdscript
const LEVELS: Array[Dictionary] = [
    {"scene": "res://scenes/levels/level_01.tscn", "name": "Level 1: ..."},
    {"scene": "res://scenes/levels/level_02.tscn", "name": "Level 2: ..."},
    {"scene": "res://scenes/levels/sandbox.tscn",  "name": "Sandbox"},
]
```
