# Level Design

Implementation-ready level designs for Makeshift. Each level includes complete seed object blueprints (matching `init_from_blueprint()` dict format), layouts, intended solution paths, and the specific interaction rules exercised.

---

## Problems with the Current Level System

### 1. No level requires creating objects

All three levels are "reach point B" puzzles solvable with a single generic creation ("wooden plank", "ladder", "trampoline"). The player learns that they CAN create objects, but never learns that WHAT they create matters. Tags, rules, behaviors, chain reactions — none of the game's interesting systems are exercised.

### 2. No environmental hazards participate in the rule system

Level 2's lava is a `ColorRect` + `Area2D` with hardcoded damage (`WorldMutations.apply_damage(body, 999.0)`). It has no tags, can't be interacted with via rules (can't freeze lava, can't extinguish it), and is invisible to the rule engine. Level 1's kill zone is the same — a pure Area2D. Environmental hazards should be tagged objects that participate in the rule system, enabling emergent counter-play (freeze the acid, evaporate the water, insulate against electricity).

### 3. Environmental objects need a new node type

Current game objects (`GameObject`, extends `RigidBody2D`) are designed for player-created objects: they have durability, can be destroyed, can be kicked, need backend sprites, show debug labels. Environmental hazards need different properties:

| Property | GameObject | Environment Object |
|----------|-----------|-------------------|
| Physics | RigidBody2D (movable) | StaticBody2D (immovable) |
| Tags | Yes | Yes — participates in rules |
| Tag mutation | Yes | Yes — can be frozen, extinguished, etc. |
| Durability | Yes (destroyable) | No (indestructible) |
| Behaviors | Yes | No |
| Sprites | Backend-generated | Level-defined (ColorRect, texture, etc.) |
| Kickable | Yes (unless HEAVY) | No |
| Field interactions | Via TagField | Needs own Area2D for player detection |

The rule system is fully duck-typed — CollisionResolver checks `has_method("get_tags")`, WorldMutations checks `has_method("take_damage")` before applying damage. An env object that implements `get_tags()` / `add_tag()` / `remove_tag()` but NOT `take_damage()` participates in rules (triggers effects on other objects) while being indestructible.

**Player detection:** Game objects detect env bodies via `body_entered` (RigidBody2D contacts StaticBody2D). But the player is a CharacterBody2D using `move_and_slide()`, which doesn't emit `body_entered`. Env objects need an Area2D child that detects player entry and routes through `CollisionResolver.resolve_collision()` for rule-based damage (e.g., `toxic_living_damage`, `corrosive_living_damage`).

### 4. No antagonistic objects in any level

The behavior system supports patrol, projectiles, chase, explosions, damage — but no level has a single object with behaviors. The game's differentiator over Scribblenauts is object autonomy, and it's completely invisible to the player.

### 5. Levels don't scaffold complexity

All three levels have the same structure (reach point B) with no progression. The player goes from "cross a gap" to "cross a gap with fire" to "climb up" without encountering any new mechanics. By the end, they've seen one tag interaction (fire + flammable) and nothing else from the 53-rule system.

---

## Design Principles

1. **Every level requires creating objects** — the core mechanic must be exercised, not optional
2. **The puzzle requires tag awareness** — "wooden plank" should not be a universal solution; material, element, and properties must matter
3. **Seed objects demonstrate mechanics** — the player should observe interactions happening before they create anything
4. **Multiple solution paths** use different rule chains (3-4 per level)
5. **Hard to cheese** — obvious/generic solutions should be suboptimal or fail; the environment should punish thoughtless creation and reward deliberate choices
6. **Progressive complexity:** environmental interactions → autonomous behaviors → chain reactions
7. **Antagonistic objects are the differentiator** — Scribblenauts did tool-use puzzles; Makeshift should feature objects that fight back

---

## Level 1: "The Acid Moat"

**Concept:** What you create matters. Material and tags determine whether your creation survives.

### Layout

```
Spawn (128, 536)                                              Goal (1100, 536)
    v                                                              v
+--------+    crate                                         +---------+
|  left  |     [ ]                                          |  right  |
|  plat  |                                                  |  plat   |
+--------+                                                  +---------+
          |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  |
          |  ~~~~ ACID POOL (env: CORROSIVE+TOXIC+LIQUID) ~|
          |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~  |
          +------------------------------------------------+
                         pit floor (below acid)

Left platform:  pos=(0, 568)     size=(384, 64)
Right platform: pos=(896, 568)   size=(384, 64)
Pit walls:      pos=(384, 568)   size=(16, 128) and pos=(880, 568) size=(16, 128)
Acid pool:      pos=(400, 632)   size=(480, 48)  — environment object with tags
Kill zone:      pos=(400, 700)   size=(480, 64)  — respawn if player falls through acid
```

The gap is ~480px — too wide to jump (player covers ~200px horizontal in a jump). The acid pool fills the bottom of the pit. A wooden crate sits on the player's platform.

### Seed Objects

```gdscript
const WOODEN_CRATE_BLUEPRINT := {
    "id": "crate_01",
    "name": "Wooden Crate",
    "tags": ["SOLID", "RIGID", "FLAMMABLE", "BREAKABLE"],
    "visual_descriptor": {
        "visual_description": "a small wooden shipping crate with rope handles",
        "size_category": "small",
    },
}
# Placed at Vector2(280, 536), not frozen — kickable (no HEAVY tag)
# Durability: 50 (BREAKABLE)
# Purpose: DEMONSTRATION OBJECT. Kick it into the acid pit.
#   corrosive_breakable_corrode fires: 15 dmg/s for 3s = 45 dmg.
#   The crate visibly takes damage and nearly dies (50 HP - 45 = 5 HP).
#   Teaches the player: "BREAKABLE things dissolve in acid."
# Too small to use as a stepping stone (small = 64px collision vs 480px gap).
```

### Environment Objects

```gdscript
# Acid pool — environment body (StaticBody2D with tags, no durability)
# Tags: ["CORROSIVE", "TOXIC", "LIQUID"]
# Visual: green ColorRect with slight transparency
# Area2D child detects player entry → CollisionResolver for rule-based damage
#
# Tag interactions when objects contact the acid:
#   corrosive_breakable_corrode: BREAKABLE objects take 15 dmg/s for 3s
#   corrosive_rigid_weaken: RIGID objects take 10 dmg/s for 3s
#   corrosive_conducting_dissolve: CONDUCTING objects take 20 dmg/s for 3s
#   corrosive_living_damage: Player takes 20 dmg on contact
#   toxic_living_damage: Player takes 10 dmg on contact (via TOXIC field)
#
# Player counter-play (if add_tag/remove_tag supported):
#   cold_liquid_freeze: COLD object near acid → acid gains FROZEN+RIGID+SOLID,
#     loses LIQUID. Frozen acid becomes a safe walkable surface!
#   heat_liquid_evaporate: HEAT_SOURCE near acid → acid loses LIQUID, gains GAS.
#     Acid evaporates but becomes toxic gas (TOXIC+GAS → toxic_gas_cloud spreads).
```

### Rules Exercised

| Rule | Trigger | What happens |
|------|---------|-------------|
| `corrosive_breakable_corrode` | CORROSIVE (acid) + BREAKABLE (crate/bridge) | 15 dmg/s for 3s = 45 total. Kills 50 HP BREAKABLE objects. |
| `corrosive_rigid_weaken` | CORROSIVE (acid) + RIGID (bridge) | 10 dmg/s for 3s = 30 total. 200 HP RIGID objects survive. |
| `corrosive_conducting_dissolve` | CORROSIVE (acid) + CONDUCTING (metal bridge) | 20 dmg/s for 3s = 60 total. 200 HP RIGID+CONDUCTING objects survive. |
| `toxic_living_damage` | TOXIC (acid) + LIVING (player) | 10 dmg if player falls in. |
| `corrosive_living_damage` | CORROSIVE (acid) + LIVING (player) | 20 dmg if player falls in. |
| `cold_liquid_freeze` | COLD (created) + LIQUID (acid) | Freezes acid solid — safe to walk on! (if env supports tag mutation) |

### Solution Paths

1. **Create a durable bridge** (intended learning path): Type "stone bridge", "metal beam", "iron plank" — anything the LLM tags as RIGID without BREAKABLE. Place across the gap. The acid's `corrosive_rigid_weaken` rule fires (10 dmg/s for 3s = 30 dmg) but the bridge has 200 HP and survives. Walk across.

2. **Learn from failure first**: Type "wooden bridge" or "plank" — likely gets BREAKABLE. Place it. `corrosive_breakable_corrode` fires: 15 dmg/s for 3s = 45 dmg. The bridge has 50 HP. It nearly dies — player can sprint across if fast, but the bridge disintegrates behind them. This teaches: material matters. Next creation: pick something sturdier.

3. **Freeze the acid** (advanced): Type "ice block" or "frozen orb" — anything with COLD tag. Place it in/near the acid. `cold_liquid_freeze` fires: acid gains FROZEN+RIGID+SOLID, loses LIQUID. The acid becomes a frozen surface — walk across! Elegant solution that uses the rule system creatively. (Requires env objects to support tag mutation.)

4. **Evaporate the acid** (risky): Create HEAT_SOURCE near acid. `heat_liquid_evaporate` removes LIQUID, adds GAS. Acid becomes toxic gas. `toxic_gas_cloud` might spread the TOXIC tag. Clears the liquid but creates a new problem. Teaches that interactions have consequences.

5. **Kick the crate to learn**: Before creating anything, kick the wooden crate into the acid. Watch it corrode. Learn that BREAKABLE+acid = bad. Then make an informed creation.

### Why This Can't Be Easily Cheesed

- **Must create**: Gap is 480px, player jumps ~200px. No seed object bridges it. The crate is too small.
- **Generic "bridge" fails**: The LLM's default wood/plank outputs get BREAKABLE → corroded. Player must specify material.
- **Can't destroy the acid**: It's an environment object with no durability.
- **Kicking doesn't help**: Nothing to kick across. Crate is too small and corrodes anyway.
- **The "right" answer requires tag thinking**: The player must reason "I need something that resists acid" → creates RIGID/non-BREAKABLE material.

### Edge Cases

- If the bridge is both BREAKABLE and RIGID, BREAKABLE takes priority for durability (50 HP). The corrosive_breakable_corrode rule fires (requires BREAKABLE on target). Bridge dies fast.
- CONDUCTING bridges (metal) take more corrosion damage (20 dmg/s vs 10 dmg/s for RIGID-only). Still survives at 200 HP, but takes more wear. Interesting nuance.
- If player creates something FLOATING over the acid, it doesn't touch the acid — no corrosion. But FLOATING objects can't support the player (player is CharacterBody2D walking on StaticBody2D/RigidBody2D surfaces, FLOATING objects have negative gravity and drift upward).
- Freezing the acid: if the COLD object is small, it might only freeze the area near it. The freeze rule removes LIQUID tag — if this is on the entire env body, ALL the acid freezes. If env objects support partial coverage, only some freezes. Implementation detail.

---

## Level 2: "The Sentry"

**Concept:** Objects can have autonomous behaviors. You create counter-objects.

### Layout

```
Spawn (128, 336)                 barricade   sentry       Goal (1100, 336)
    v                               |          |              v
+-----+                           [==]   +---[T]---+   +-----+
|     |                            ||    | pedestal |   |     |
|     +----------------------------------------------------------+
|                         main floor                             |
+----------------------------------------------------------------+

Main floor:    pos=(0, 400)      size=(1280, 64)
Pedestal:      pos=(620, 340)    size=(128, 60)
```

### Seed Objects

```gdscript
const SENTRY_BLUEPRINT := {
    "id": "sentry_01",
    "name": "Sentry Turret",
    "tags": ["SOLID", "RIGID", "HEAVY", "HEAT_SOURCE"],
    "visual_descriptor": {
        "visual_description": "a mechanical turret with a rotating cannon barrel mounted on a metal base",
        "size_category": "medium",
    },
    "behaviors": [
        {
            "trigger": "ALWAYS",
            "action": "PATROL",
            "target": "SELF",
            "speed": "SLOW",
        },
        {
            "trigger": "ON_PROXIMITY",
            "action": "SPAWN_PROJECTILE",
            "target": "NEAREST_PLAYER",
            "intensity": "MEDIUM",
            "range": "FAR",
            "interval": "SLOW",
        },
    ],
}
# Placed at Vector2(684, 300), not frozen — patrols on pedestal
# Durability: 200 (RIGID). HEAVY so kicks do damage but no knockback.
# Projectiles: base tags [SOLID, LIGHT, BREAKABLE] + payload HOT (from HEAT_SOURCE via PAYLOAD_TAG_MAP).
#   Speed 250 px/s, durability 15, lifetime 2.5s.
#   Projectile hits player: behavior deals MEDIUM damage (20) + hot_living_burn rule (5 dmg) = 25 per hit.
# Behaviors: 2 of 3 slots used.

const BARRICADE_BLUEPRINT := {
    "id": "barricade_01",
    "name": "Wooden Barricade",
    "tags": ["SOLID", "RIGID", "FLAMMABLE", "BREAKABLE"],
    "visual_descriptor": {
        "visual_description": "a tall wooden barricade made of rough planks nailed together",
        "size_category": "large",
    },
}
# Placed at Vector2(420, 280), frozen in place (freeze=true, FREEZE_MODE_STATIC)
# Durability: 50 (BREAKABLE).
# Provides initial cover. At 264px from turret, well outside HEAT_SOURCE field
#   range (CLOSE=64px), so barricade won't ignite from turret's field.
# Turret projectiles carry HOT (not HEAT_SOURCE), so no ignition on hit either.

const SHIELD_BLUEPRINT := {
    "id": "shield_01",
    "name": "Metal Shield",
    "tags": ["SOLID", "RIGID", "REFLECTIVE", "CONDUCTING"],
    "visual_descriptor": {
        "visual_description": "a polished metal shield with a reflective surface",
        "size_category": "medium",
    },
}
# Placed at Vector2(350, 368), not frozen — kickable (no HEAVY tag)
# Durability: 200 (RIGID).
# REFLECTIVE → reflective_heat_reflect deals 10 dmg back to HEAT_SOURCE on contact.
# CONDUCTING adds interaction options (electric conduction, magnetic attraction).
```

### Rules Exercised

| Rule | Trigger | What happens |
|------|---------|-------------|
| `hot_living_burn` | HOT (projectile) + LIVING (player) | 5 dmg per projectile hit (on top of 20 behavior damage) |
| `reflective_heat_reflect` | REFLECTIVE (shield) + HEAT_SOURCE (turret) | 10 dmg reflected to turret on contact |
| `liquid_heat_extinguish` | LIQUID (created) + HEAT_SOURCE (turret) | Removes HEAT_SOURCE+HOT — disarms projectile payload |
| `explosive_heat_detonate` | EXPLOSIVE (created) + HEAT_SOURCE (turret) | Massive explosion, 80 dmg + 500 force to turret |

### Solution Paths

1. **Kick the shield** toward the turret: REFLECTIVE + HEAT_SOURCE → `reflective_heat_reflect` → 10 dmg per contact. Turret has 200 HP so this alone is slow, but the shield physically blocks projectiles.

2. **Create water/liquid**: "bucket of water", "water balloon" — LIQUID tag. Place near turret. `liquid_heat_extinguish` removes HEAT_SOURCE and HOT. Turret still patrols and shoots, but projectiles lose their HOT payload. Behavior damage (20) still applies, but no burn.

3. **Create explosive**: "TNT", "bomb" — EXPLOSIVE tag. Kick toward turret. `explosive_heat_detonate` → 99999 dmg to explosive + 80 dmg to turret. Turret has 200 HP, takes 80 → survives with 120 HP. Combine with kicks or a second explosive.

4. **Sprint past**: Projectiles at SLOW interval (3s), FAR range (256px). Player speed 300 px/s. ~680px from barricade to goal = ~2.3s. One projectile hit (25 dmg). Viable but not rewarding.

5. **Create INSULATING barrier**: Blocks heat/electric rule interactions. Place between player and turret as fireproof cover.

### Edge Cases

- Turret patrols on pedestal: SLOW speed = 60 px/s max. Pedestal is 128px wide; physics constrain it.
- Projectiles are LIGHT → WIND_SOURCE could blow them off course.
- If turret falls off pedestal (unlikely — HEAVY + slow patrol), it continues shooting from ground. Not game-breaking.
- Barricade is safe from turret's heat field (264px apart, field range 64px). Projectiles carry HOT, not HEAT_SOURCE — no ignition rule fires on barricade from projectile impact.

---

## Level 3: "The Chain Reaction"

**Concept:** Cascading tag propagation. One action triggers a chain of interactions.

### Layout

```
                                    +-------+
                                    | goal  |  Goal (1050, 100)
                              +-----+  area +-----+
                              | door [======] tnt  |
                              |      +-------+     |
                              | upper platform     |
                              +--------+-----------+
                                       |
                                  pipe4 o  (700, 280)
                                       |
                                  pipe3 o  (650, 360)
                                       |
                                  pipe2 o  (600, 440)
                                       |
                                  pipe1 o  (550, 520)
                                       |
                                   ~~gap~~ (~100px, just beyond cascade radius)
                                       |
                               battery [B]  (420, 570)
Spawn (128, 536)
    v
+----------------------------------------------------------------+
|                         main floor                             |
+----------------------------------------------------------------+

Main floor:      pos=(0, 600)     size=(1280, 64)
Upper platform:  pos=(600, 200)   size=(512, 64)
Pipe ledges:     pos=(550, 520) size=(32, 16)  — pipe1
                 pos=(600, 440) size=(32, 16)  — pipe2
                 pos=(650, 360) size=(32, 16)  — pipe3
                 pos=(700, 280) size=(32, 16)  — pipe4
```

Pipes rest on tiny ledges forming a vertical chain. The battery is on the main floor. The gap between battery and pipe1 is ~130px (cascade radius is 96px — just out of range).

### Seed Objects

```gdscript
const METAL_DOOR_BLUEPRINT := {
    "id": "metal_door_01",
    "name": "Metal Door",
    "tags": ["SOLID", "RIGID", "HEAVY", "CONDUCTING", "BREAKABLE"],
    "visual_descriptor": {
        "visual_description": "a thick reinforced metal door with rivets and a heavy lock",
        "size_category": "large",
    },
}
# Placed at Vector2(800, 150), frozen in place — blocks the goal area
# Durability: 50 (BREAKABLE takes priority over RIGID)
# CONDUCTING so it participates in electrical chains
# BREAKABLE so explosion destroys it

const TNT_BLUEPRINT := {
    "id": "tnt_01",
    "name": "TNT Barrel",
    "tags": ["SOLID", "RIGID", "EXPLOSIVE", "BREAKABLE", "FLAMMABLE"],
    "visual_descriptor": {
        "visual_description": "a red barrel marked with TNT and a fuse on top",
        "size_category": "medium",
    },
}
# Placed at Vector2(900, 170), frozen in place — adjacent to metal door
# Durability: 50 (BREAKABLE)
# EXPLOSIVE + ELECTRIC → explosive_electric_detonate (99999 dmg self, 500 force)
# EXPLOSIVE + HEAT_SOURCE → explosive_heat_detonate (99999 dmg self, 80 dmg + 500 force)

const PIPE_BLUEPRINT := {
    "id": "metal_pipe",
    "name": "Metal Pipe",
    "tags": ["SOLID", "RIGID", "CONDUCTING"],
    "visual_descriptor": {
        "visual_description": "a straight copper pipe section with green patina",
        "size_category": "small",
    },
}
# 4 instances, each frozen in place on their ledge
# Positions: (550, 510), (600, 430), (650, 350), (700, 270)
# Each within 96px cascade radius of the next
# Durability: 200 (RIGID)

const BATTERY_BLUEPRINT := {
    "id": "battery_01",
    "name": "Battery",
    "tags": ["SOLID", "RIGID", "ELECTRIC", "CONDUCTING"],
    "visual_descriptor": {
        "visual_description": "a large industrial battery with positive and negative terminals",
        "size_category": "medium",
    },
}
# Placed at Vector2(420, 568), not frozen — kickable (not HEAVY)
# Gap to pipe1: ~130px. Cascade radius 96px. Just out of range.
# Player must bridge the gap with a CONDUCTING object.
```

### Chain Reaction Sequence

The cascade depth limit is 3, so instant cascade only reaches pipe2. The remaining pipes electrify via periodic field ticks (every 2s), creating a dramatic real-time propagation:

| Time | Event |
|------|-------|
| 0s | Player places CONDUCTING bridge. Battery contact → cascade: bridge → pipe1 → pipe2 (depth 3, limit reached). |
| 2s | Pipe2's periodic field tick → `electric_conducting_electrify` on pipe3 (new chain, depth 0). |
| 4s | Pipe3's field → electrifies pipe4. |
| 6s | Pipe4's field → hits TNT. `explosive_electric_detonate` fires. TNT destroyed (99999 dmg). 500 force impulse. |
| 6s | TNT cascade: `explosive_breakable_destroy` fires on metal door → 99999 dmg. Door destroyed. Path cleared. |

### Solution Paths

1. **Bridge the gap** (intended): Create "copper wire", "metal rod", "iron chain" — anything CONDUCTING. Place between battery and pipe1. Watch electricity climb the chain over ~6 seconds.

2. **Direct ignition**: Create HEAT_SOURCE and climb to TNT level. Place next to TNT. `explosive_heat_detonate` fires. Requires two creations (climbing + ignition). More expensive.

3. **Corrosive destruction**: Create "acid" (CORROSIVE). Place near door. `corrosive_breakable_corrode` → 15 dmg/s for 3s = 45 dmg on 50 HP door. Nearly kills it; a few kicks finish. Bypasses the chain entirely.

4. **Kick the battery**: Battery is kickable (not HEAVY). Kick it toward pipe1. If it lands within 96px, the chain starts without creating anything. Requires precision — fun speedrun path.

### Edge Cases

- If player creates a CONDUCTING+BREAKABLE object as the bridge, `electric_breakable_damage` (30 dmg) might destroy it (50 HP BREAKABLE) before cascade completes. RIGID CONDUCTING objects are safer.
- Player near electrified pipes: `electric_living_shock` → 30 dmg. Stay at ground level.
- Battery kicked too far past pipe1: still works if it lands near any pipe.

### Cascade Permanence Design Decision

Current code: periodic field ticks use `cascade_depth=0`, making field-applied ELECTRIC tags permanent. This means pipes stay electrified forever after the chain completes.

Alternative: change field ticks to `cascade_depth=1` → tags get 10s decay, re-applied by field every 2s → persist while source exists, fade when source dies. Either works for this level — resolve during implementation based on gameplay feel.

---

## Level 4: "The Living Maze" (Stretch)

**Concept:** Multiple behavioral creatures. Diagnose each obstacle's tags and create the correct counter.

### Layout

Three rooms connected by narrow corridors. Each room has one behavioral "creature" guarding the passage.

```
+-------+    +--------+    +--------+    +-------+
| Room 1|----| Room 2 |----| Room 3 |----|  Goal |
| Slime |    | Guard  |    | Magnet |    |       |
+-------+    +--------+    +--------+    +-------+
  Spawn
```

### Room 1: Toxic Slime

```gdscript
const TOXIC_SLIME_BLUEPRINT := {
    "id": "toxic_slime_01",
    "name": "Toxic Slime",
    "tags": ["SOLID", "FLEXIBLE", "TOXIC", "LIVING", "BOUNCY"],
    "visual_descriptor": {
        "visual_description": "a bubbling green slime creature leaving a trail of toxic residue",
        "size_category": "medium",
    },
    "behaviors": [
        {
            "trigger": "ALWAYS",
            "action": "PATROL",
            "target": "SELF",
            "speed": "SLOW",
        },
        {
            "trigger": "ON_PROXIMITY",
            "action": "MOVE_TOWARD",
            "target": "NEAREST_PLAYER",
            "speed": "MEDIUM",
            "range": "MEDIUM",
        },
    ],
}
# Durability: 100 (FLEXIBLE). Patrols corridor, chases player on proximity.
# TOXIC field (MEDIUM range=96px, periodic 2s): toxic_living_damage → 10 dmg to player.
# BOUNCY so it rebounds off walls.
# Behaviors: 2 of 3 slots used.
```

**Solutions:** Kick it repeatedly (10 dmg each, 100 HP = 10 kicks). Create SHARP/CORROSIVE objects to deal damage. Sprint past during patrol gap. Create a barrier to block it.

### Room 2: Fire Guardian

```gdscript
const FIRE_GUARDIAN_BLUEPRINT := {
    "id": "fire_guardian_01",
    "name": "Fire Guardian",
    "tags": ["SOLID", "RIGID", "HEAVY", "HEAT_SOURCE", "HOT"],
    "visual_descriptor": {
        "visual_description": "a stone gargoyle with flames pouring from its mouth",
        "size_category": "medium",
    },
    "behaviors": [
        {
            "trigger": "ON_PROXIMITY",
            "action": "SPAWN_PROJECTILE",
            "target": "NEAREST_LIVING",
            "intensity": "MEDIUM",
            "range": "FAR",
            "interval": "MEDIUM",
        },
    ],
}
# Stationary. Shoots HOT projectiles at 1.5s interval (MEDIUM).
# Behaviors: 1 of 3 slots used.
```

**The dilemma:** The room exit is elevated. A FLAMMABLE wooden wall provides the climbing surface. The guardian's field (HEAT_SOURCE, CLOSE=64px) will ignite anything FLAMMABLE within range. Player must either extinguish the guardian (LIQUID), shield the wall, or create a non-FLAMMABLE climbing alternative.

### Room 3: Magnetic Trap

```gdscript
const MAGNET_PILLAR_BLUEPRINT := {
    "id": "magnet_pillar",
    "name": "Magnetic Pillar",
    "tags": ["SOLID", "RIGID", "HEAVY", "MAGNETIC"],
    "visual_descriptor": {
        "visual_description": "a tall iron pillar crackling with magnetic energy",
        "size_category": "large",
    },
}
# 2 instances on opposite walls, frozen in place.

const METAL_DEBRIS_BLUEPRINT := {
    "id": "metal_debris",
    "name": "Metal Fragment",
    "tags": ["SOLID", "RIGID", "CONDUCTING", "SHARP"],
    "visual_descriptor": {
        "visual_description": "a jagged metal fragment with sharp edges",
        "size_category": "small",
    },
}
# 4-5 instances scattered in corridor. CONDUCTING → pulled by MAGNETIC field.
# SHARP → sharp_living_cut (25 dmg) on player contact.
```

**Solutions:** Create INSULATING objects (blocks magnetic interaction). Create WIND_SOURCE to overpower pull. Sprint through gaps in debris pattern. Create a HEAVY shield (debris bounces off).

---

## Level 5: "Rube Goldberg" (Stretch)

**Concept:** Mastery. Three chain reaction types stacked vertically.

Vertical tower with 3 locked gates. Each gate has a different trigger mechanism:

**Gate 1 (bottom):** FLAMMABLE fuse trail → fire reaches TNT → explosion opens gate.
- Rules: `heat_flammable_ignite` (cascade) → `explosive_heat_detonate`.
- Player creates HEAT_SOURCE to light the fuse.

**Gate 2 (middle):** CONDUCTING wire chain → electricity reaches explosive charge.
- Rules: `electric_conducting_electrify` (cascade) → `explosive_electric_detonate`.
- Player bridges a gap with CONDUCTING object.

**Gate 3 (top):** FROZEN ice dam holding a HEAVY boulder above the gate lock.
- Rules: `heat_frozen_melt` → gravity → `heavy_breakable_crush`.
- Player creates HEAT_SOURCE to melt the dam, releasing the boulder.

Each stage demonstrates a different interaction category (fire, electricity, physics).

---

## Sandbox Level

**Concept:** Open experimentation. No objective. Diverse seed objects to play with.

### Layout

```
+-----------------------------------------------------------------+
|                                                                 |
|                     large open area                             |
|                                                                 |
|   [seed objects scattered across the floor, ~200px apart]       |
|                                                                 |
+-----------------------------------------------------------------+

Floor: pos=(0, 600)  size=(2560, 64)
Left wall:  pos=(0, 0)    size=(32, 664)
Right wall: pos=(2528, 0) size=(32, 664)
```

No goal area. No level completion. Player stays until they return to menu.

### Seed Objects

One representative from each tag category:

```gdscript
const SANDBOX_SEEDS: Array[Dictionary] = [
    # Fire / Heat
    {
        "id": "sandbox_torch",
        "name": "Torch",
        "tags": ["SOLID", "RIGID", "HEAT_SOURCE", "HOT", "GLOWING", "LIGHT"],
        "visual_descriptor": {
            "visual_description": "a wooden torch with a bright orange flame",
            "size_category": "small",
        },
    },
    # Ice / Cold
    {
        "id": "sandbox_ice",
        "name": "Ice Block",
        "tags": ["SOLID", "RIGID", "FROZEN", "COLD", "SLIPPERY", "BREAKABLE"],
        "visual_descriptor": {
            "visual_description": "a block of clear blue ice",
            "size_category": "medium",
        },
    },
    # Electricity
    {
        "id": "sandbox_battery",
        "name": "Battery",
        "tags": ["SOLID", "RIGID", "ELECTRIC", "CONDUCTING"],
        "visual_descriptor": {
            "visual_description": "a car battery with metal terminals",
            "size_category": "small",
        },
    },
    # Flammable target
    {
        "id": "sandbox_crate",
        "name": "Wooden Crate",
        "tags": ["SOLID", "RIGID", "FLAMMABLE", "BREAKABLE"],
        "visual_descriptor": {
            "visual_description": "a wooden shipping crate with rope handles",
            "size_category": "medium",
        },
    },
    # Explosive
    {
        "id": "sandbox_tnt",
        "name": "TNT",
        "tags": ["SOLID", "RIGID", "EXPLOSIVE", "FLAMMABLE", "BREAKABLE"],
        "visual_descriptor": {
            "visual_description": "a bundle of dynamite sticks with a fuse",
            "size_category": "small",
        },
    },
    # Wind
    {
        "id": "sandbox_fan",
        "name": "Fan",
        "tags": ["SOLID", "RIGID", "WIND_SOURCE", "LIGHT"],
        "visual_descriptor": {
            "visual_description": "a large industrial fan with spinning blades",
            "size_category": "medium",
        },
    },
    # Magnetic
    {
        "id": "sandbox_magnet",
        "name": "Magnet",
        "tags": ["SOLID", "RIGID", "MAGNETIC", "HEAVY"],
        "visual_descriptor": {
            "visual_description": "a large red horseshoe magnet",
            "size_category": "medium",
        },
    },
    # Conducting target
    {
        "id": "sandbox_metal_plate",
        "name": "Metal Plate",
        "tags": ["SOLID", "RIGID", "HEAVY", "CONDUCTING"],
        "visual_descriptor": {
            "visual_description": "a flat steel plate with a brushed finish",
            "size_category": "medium",
        },
    },
    # Toxic
    {
        "id": "sandbox_acid",
        "name": "Acid Puddle",
        "tags": ["LIQUID", "TOXIC", "CORROSIVE"],
        "visual_descriptor": {
            "visual_description": "a bubbling pool of green acid",
            "size_category": "small",
        },
    },
    # Bouncy
    {
        "id": "sandbox_ball",
        "name": "Rubber Ball",
        "tags": ["SOLID", "FLEXIBLE", "BOUNCY", "LIGHT"],
        "visual_descriptor": {
            "visual_description": "a bright red rubber ball",
            "size_category": "small",
        },
    },
    # Living target (for behavior interactions)
    {
        "id": "sandbox_critter",
        "name": "Critter",
        "tags": ["SOLID", "FLEXIBLE", "LIVING", "LIGHT"],
        "visual_descriptor": {
            "visual_description": "a small furry creature with big eyes",
            "size_category": "tiny",
        },
        "behaviors": [
            {
                "trigger": "ON_DAMAGED",
                "action": "MOVE_AWAY",
                "target": "NEAREST_OBJECT",
                "speed": "FAST",
            },
        ],
    },
]
```

### Implementation Notes

- BaseLevel requires a `$Goal` Area2D. Sandbox needs either: a dummy unreachable goal, or BaseLevel modified to make goal optional.
- Budget should be generous — either increase session budget or make sandbox use a separate budget.
- Consider a "reset" button that respawns seed objects.
- Seed objects spaced ~200px apart so they don't immediately interact.

---

## GameManager Updates

```gdscript
const LEVELS: Array[Dictionary] = [
    {"scene": "res://scenes/levels/level_01.tscn", "name": "Level 1: The Acid Moat"},
    {"scene": "res://scenes/levels/level_02.tscn", "name": "Level 2: The Sentry"},
    {"scene": "res://scenes/levels/level_03.tscn", "name": "Level 3: The Chain Reaction"},
    {"scene": "res://scenes/levels/sandbox.tscn", "name": "Sandbox"},
]
```

---

## Implementation Checklist

### Prerequisites
- [x] Implement `EnvironmentBody` node type (StaticBody2D with tags, no durability)
- [x] Verify EnvironmentBody works with CollisionResolver (duck-typed `get_tags()`)
- [x] Add Area2D player detection to EnvironmentBody (routes through CollisionResolver)
- [x] Add `_create_env_body()` helper to BaseLevel

### Per level
- [x] Level 1 "The Acid Moat" — `.gd` rewritten (acid pool env body, wooden crate seed, kill zone)
- [x] Level 1 — `.tscn` updated (spawn/goal positions, objective text)
- [x] Level 2 "The Sentry" — `.gd` rewritten (sentry turret with PATROL+SPAWN_PROJECTILE, frozen barricade, kickable shield)
- [x] Level 2 — `.tscn` updated (spawn/goal positions, objective text)
- [ ] Level 3 "The Chain Reaction" — `.gd` not yet rewritten
- [ ] Playtest each solution path
- [ ] Verify seed object durability values (BREAKABLE=50, RIGID=200, FLEXIBLE=100, default=150)
- [ ] Verify behavior counts are within limits (max 3 per object)
- [ ] Verify tag costs are within limits (max 10)
- [ ] Test that frozen objects (`freeze=true`) behave correctly with field interactions

### Sandbox
- [ ] Create `sandbox.tscn` and `sandbox.gd`
- [ ] Handle missing Goal node in BaseLevel (or use dummy goal)
- [ ] Add to GameManager.LEVELS
- [ ] Test all seed object interactions
