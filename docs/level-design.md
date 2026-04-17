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

## Core Mechanics for Level Design

The interaction system provides:
- **State propagation**: objects with `initial_states` spread those states to nearby objects with matching `susceptible_states` every 2s
- **Essential-state destruction**: objects with `initial_states` are destroyed when all initial states are removed (fire extinguished = destroyed)
- **Object behavior**: per-pair staged evaluation — active objects (approach/flee) and reactive objects (bomb, fan) use composite actions (damage/heal/consume/push + state modifier)

Level puzzles should be designed around these mechanics. Examples:
- A fire (initial_states=[burning]) spreads to wood (susceptible_states=[burning]) → fire spread puzzle
- Ice (initial_states=[frozen]) — water extinguishes burning AND freezes susceptible objects
- Creating a wet object near electrified ones is dangerous (wet susceptible to electrified)
- Creatures with high priority toward specific states (firefighter → burning) create natural puzzles

**Seed object blueprints** use the `GameObjectBlueprint` format with `initial_states`, `susceptible_states`, `active`, `durability`, and `affordance`. See `models/blueprint.py` for the complete structure.

---

## BaseLevel API

All levels extend `BaseLevel` (`scenes/levels/BaseLevel.cs`). Available helpers:

```csharp
// Spawn a pre-defined game object from blueprint dict
protected Node SpawnGameObject(Godot.Collections.Dictionary blueprint, Vector2 pos)

// Create a kill zone (999 dmg to objects, respawns player)
protected void CreateKillZone(Vector2 pos, Vector2 size)

// Create a static platform from texture
protected void CreatePlatform(Vector2 pos, Vector2 size, Texture2D? texture = null)

// Create a non-player environment body (acid moat, etc.)
protected EnvironmentBody CreateEnvBody(Vector2 pos, Vector2 size, string name,
    Godot.Collections.Dictionary bp, Color color, bool solid = true)
```

`BaseLevel` requires a `Goal` Area2D node and a `SpawnPoint` Marker2D in the scene for goal detection and player respawn.

### Seed Object Blueprint Format

Blueprints are `Godot.Collections.Dictionary` (JSON-compatible). Use `SpawnGameObject()` to place them. State IDs: 1=burning, 2=frozen, 3=wet, 4=electrified.

```csharp
// In a Level subclass _Ready() override:
var fireBp = new Godot.Collections.Dictionary
{
    ["id"]                    = "fire_01",
    ["name"]                  = "Fire",
    ["description"]           = "a small campfire",
    ["visual_description"]    = "a small orange and yellow campfire with flickering flames",
    ["physics"]               = new Godot.Collections.Dictionary {
        ["mass_kg"]   = 0.1f,
        ["height_cm"] = 40,
        ["surface"]   = 0,   // 0=slippery 1=normal 2=sticky
        ["bounce"]    = 0,
        ["gravity"]   = 10,  // fire rises
    },
    ["durability"]            = 0,   // fragile (5 HP)
    ["affordance"]            = 3,   // 3=nothing
    ["active"]                = false,
    ["speed"]                 = 2,
    ["initial_states"]        = new Godot.Collections.Array { 1 },  // burning
    ["susceptible_states"]    = new Godot.Collections.Array(),
    ["destruction_result_name"] = "ash",
};
SpawnGameObject(fireBp, new Vector2(400, 300));
```

### GameManager Level Registration

Levels are registered as `LevelInfo` records in `GameManager.Levels` (`autoloads/GameManager.cs`):

```csharp
public static readonly LevelInfo[] Levels =
[
    new("res://scenes/levels/level_01.tscn", "Level 1: The Acid Moat"),
    new("res://scenes/levels/level_02.tscn", "Level 2: The Sentry"),
    new("res://scenes/levels/level_03.tscn", "Level 3: Reach the Top"),
];
```

Add new level scene files and register them here to make them accessible from the main menu.
