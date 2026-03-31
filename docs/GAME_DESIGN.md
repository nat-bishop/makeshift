# Game Design

## Core Concept

"Scribblenauts meets Terraria" — a 2D physics sandbox where players type text descriptions to create game objects. An LLM (Gemini) interprets descriptions into tagged blueprints with visual descriptors and autonomous behaviors. Gemini image generation produces sprites. Objects interact through a tag-based rule system and behavior system, enabling emergent puzzle-solving: fire melts ice, a dragon patrols and breathes fire, a time bomb explodes after a delay.

Tags define what an object *is*; behaviors define what it *does*. Each object gets 1-4 tags and an optional signature behavior — enough to express a rich concept while keeping LLM output focused. Common behaviors (chase, flee, wander, detonate) are tag-implied and don't need explicit authoring.

## Tag System

27 tags across 7 categories (+ 2 internal-only). Tags are the atomic unit of the entire game — they drive physics, interactions, durability, and implied behaviors.

### Categories

| Category | Tags |
|----------|------|
| Physical State | LIQUID, GAS, RIGID, HEAVY, LIGHT |
| Temperature | FROZEN, COLD, MOLTEN |
| Energy | FLAMMABLE, HEAT_SOURCE, ELECTRIC, MAGNETIC, EXPLOSIVE |
| Surface | SHARP, STICKY, REFLECTIVE |
| Mechanical | BOUNCY, BREAKABLE |
| Environmental | FLOATING, WIND_SOURCE, ACIDIC, TOXIC, WET |
| Special | LIVING, METALLIC, INSULATING, HOSTILE |
| Internal-only | HOT (rule-applied burn), GLOWING (legacy, unused) |

**Pruned tags**: SOLID (82% filler, 0 rules — implicit default), FLEXIBLE (1 unintuitive rule), SLIPPERY (0% generated, overlaps FROZEN physics). **Renamed**: CORROSIVE→ACIDIC, CONDUCTING→METALLIC (LLM-friendly names boost generation accuracy).

WET (Environmental) is a state tag applied automatically by nearby LIQUID objects (15s duration). It amplifies interactions: ELECTRIC shock deals 45 dmg instead of 30, freezing occurs faster near COLD, and fire is resisted. Contradicts MOLTEN and HEAT_SOURCE. Physics effect: linear friction 0.1 (slippery when wet). Field tag (CLOSE, periodic).

HOSTILE (Special) is a danger-aura field tag — it deals 20 damage + knockback (150 force vs LIVING, 100 vs BREAKABLE) to everything in CLOSE range on a 2s tick. HOSTILE + HOSTILE clash rule deals 15 dmg to both sides + 120 force. This makes hostile objects into area-denial threats rather than simple contact hazards. Tags handle all contact damage; behaviors handle autonomous proactive actions.

STICKY (Surface) is a continuous field tag (CLOSE range) that slows everything nearby to 25% speed — applying `linear_damp=12.0` to RigidBody2D objects and a speed modifier to the player. Area denial trap mechanic.

REFLECTIVE (Surface) bounces heat, electricity, and resists acid — the `reflective_acidic_resist` rule removes ACIDIC from the attacker on contact.

EXPLOSIVE is the highest-impact single tag: area damage on heat or electricity contact. Tag-implied behavior: detonates when damaged (ON_DAMAGED → EXPLODE). The LLM can override the trigger via the signature behavior.

### Contradiction Pairs (13)

Tags that can't coexist on the same object:

```
FROZEN↔MOLTEN    FROZEN↔HOT        COLD↔HOT         COLD↔MOLTEN
HEAVY↔LIGHT      LIQUID↔RIGID      GAS↔RIGID        GAS↔HEAVY
LIQUID↔GAS       METALLIC↔INSULATING
HEAT_SOURCE↔FLAMMABLE              WET↔MOLTEN       WET↔HEAT_SOURCE
```

Enforced by Pydantic validators on `CreatorOutput`. Violations trigger `ModelRetry` with feedback to the LLM, not hard failures.

## Rule System

50 `InteractionRule` definitions in `engine/rules_data.py`. Each rule specifies:
- Required tags on object A and/or B
- `execution_order` (higher fires first)
- Whether bidirectional (A↔B or only A→B)
- Whether cascade-eligible (can trigger chain reactions)
- `trigger_mode`: CONTACT (default) or FIELD
- Effects to apply

### Design Philosophy

**Intuitive**: Rules should match player intuition. Fire + flammable = ignite. Water + fire = extinguish. Sharp + breakable = damage.

**Chain reactions**: Cascade-eligible rules create emergent gameplay. Igniting one flammable object spreads HEAT_SOURCE to neighbors, which may ignite more flammable objects. Depth-limited to 3 to prevent infinite loops.

**Distance-based interactions**: ~24 of 50 rules are annotated `trigger_mode=FIELD`. These fire both at range (via `TagField`) and on direct contact. The rule declares *whether* an interaction works at distance; `FieldConfig` declares *how far* and *how* for the emitting tag. Separating these concerns avoids duplicating range values across rules that share the same emitting tag.

**Counters exist**: Every powerful interaction has a counter. INSULATING blocks ELECTRIC propagation. REFLECTIVE bounces HEAT_SOURCE. LIQUID extinguishes HEAT_SOURCE. This creates a rock-paper-scissors dynamic.

### Rule Categories

| Category | Example rules | Cascade? | Field? |
|----------|--------------|----------|--------|
| Fire/Heat | HEAT_SOURCE + FLAMMABLE → ignite, + FROZEN → melt, LIQUID + HEAT_SOURCE → extinguish | Yes (ignite) | Yes |
| Temperature | COLD + LIQUID → freeze, COLD + MOLTEN → solidify, HOT + LIVING → burn | No | Yes |
| Electricity | ELECTRIC + METALLIC → electrify + propagate, + LIQUID → electrify, + FLAMMABLE → spark ignition, + GAS → ionize plasma | Yes (conduction, spark, ionize) | Yes (conduction, liquid, gas) |
| Physical | SHARP + BREAKABLE → damage, HEAVY + BREAKABLE → damage, BOUNCY + RIGID → bounce | No | No |
| Hostile | HOSTILE + BREAKABLE/LIVING → 20 dmg + knockback (field, periodic), HOSTILE + HOSTILE → 15 dmg + 120 force | No | Yes |
| WET | LIQUID → adds WET (15s), WET + ELECTRIC → 45 dmg, WET + COLD → faster freeze, HEAT_SOURCE → removes WET | No | Yes (LIQUID, WET) |
| Counter | INSULATING blocks ELECTRIC, REFLECTIVE reflects HEAT_SOURCE/ELECTRIC/acid (reflective_acidic_resist) | No | No |
| Magnetic/Wind | MAGNETIC + METALLIC → attract, WIND_SOURCE + LIGHT/GAS/FLOATING → push | No | Yes |
| Environmental | ACIDIC + BREAKABLE → corrode, TOXIC + LIVING → damage | No | Yes (TOXIC) |

### Field Modes

Rules with `trigger_mode=FIELD` execute via two paths:
- **Continuous** (WIND_SOURCE, MAGNETIC, STICKY): `apply_central_force()` per physics frame via `TagField._physics_process`. Forces are tuned for per-frame application. STICKY applies `linear_damp=12.0` and a player speed modifier to slow nearby objects to 25%.
- **Periodic** (HEAT_SOURCE, HOT, ELECTRIC, COLD, TOXIC, LIQUID, HOSTILE, WET): `resolve_collision()` on a 2s timer. Full rule engine evaluation, subject to the 0.5s pair cooldown.

### Wildcard Rules

Rules with empty `tags_required_b` match any second object. Used for unconditional effects.

## Behavior System

Two layers: **tag-implied behaviors** (automatic) and an optional **signature behavior** (LLM-authored).

### Tag-Implied Behaviors

Common patterns are derived from tags at blueprint creation — no LLM authoring needed:

| Tag Combination | Implied Behavior |
|---|---|
| HOSTILE + LIVING | Chase nearest living (ALWAYS → MOVE_TOWARD) |
| HOSTILE + LIVING | Flee when hurt (ON_HEALTH_LOW → MOVE_AWAY) |
| LIVING (no HOSTILE) | Wander (ALWAYS → PATROL) |
| EXPLOSIVE | Detonate when damaged (ON_DAMAGED → EXPLODE) |

### Signature Behavior

One optional LLM-authored behavior per object — the unique "twist" that makes this object different from others with the same tags. Format: `TRIGGER -> ACTION` or `TRIGGER -> ACTION -> TARGET, power=POWER`. Targets auto-inferred when omitted.

If the signature shares a trigger with an implied behavior, it overrides that specific implied behavior (per-trigger, not all-or-nothing). Other implied behaviors survive.

### LLM Vocabulary

7 triggers: ALWAYS, ON_TIMER, ON_PROXIMITY, ON_CONTACT, ON_DAMAGED, ON_HEALTH_LOW, ON_TAG_ADDED(TAG)

7 actions: MOVE_TOWARD, MOVE_AWAY, SPAWN_PROJECTILE, EXPLODE, HEAL, ADD_TAGS, SELF_DESTRUCT

3 targets: SELF, NEAREST_LIVING, NEAREST_PLAYER (+ CONTACT_BODY auto-inferred for contact triggers)

Engine-internal actions (PATROL, APPLY_FORCE, ATTRACT, REMOVE_TAGS) and triggers (ON_CREATE, ON_DESTROY) exist for tag-implied behaviors but are not in the LLM vocabulary.

### Composing Tags and Behaviors

The tag and behavior systems interact through `ON_TAG_ADDED` triggers. This bridges the rule engine (which mutates tags on collision) to the behavior system:

- Rule engine adds HOT to a bomb → ON_TAG_ADDED(HOT) triggers EXPLODE
- Rule engine ignites an object → ON_TAG_ADDED(HEAT_SOURCE) triggers MOVE_AWAY from heat
- Behavior adds ELECTRIC tag → rule engine propagates it to METALLIC neighbors

### Design Examples

**Dragon** (aggressor):
- Tags: LIVING, HOSTILE, HEAT_SOURCE, HEAVY
- Signature: ON_PROXIMITY → SPAWN_PROJECTILE → NEAREST_LIVING, power=high
- Implied: chase (HOSTILE+LIVING), flee when hurt (HOSTILE+LIVING). Signature adds ranged fire breath.

**Time Bomb** (delayed threat):
- Tags: EXPLOSIVE, RIGID, BREAKABLE
- Signature: ON_TIMER → SELF_DESTRUCT
- Implied: detonate on damage (EXPLOSIVE). Signature adds timed detonation as alternative trigger.

**Guard Dog** (reactive defender):
- Tags: LIVING, SHARP, HOSTILE, RIGID
- Signature: null
- Implied: chase (HOSTILE+LIVING), flee when hurt. SHARP cuts on contact, HOSTILE field damages nearby. Tags fully express this object.

**Reactive Bomb** (tag-triggered via rule engine):
- Tags: EXPLOSIVE, FLAMMABLE, BREAKABLE
- Signature: ON_TAG_ADDED(HEAT_SOURCE) → EXPLODE
- Fire adds HEAT_SOURCE via rules → triggers signature EXPLODE. Overrides the implied ON_DAMAGED detonation with a more specific trigger.

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

Walking into a `RigidBody2D` applies a continuous impulse of **80 units** in the collision direction. Only applies to `is_passively_pushable()` objects: LIGHT-tagged or tiny-sized, excluding HEAVY. Most objects require a deliberate kick to move.

### Kick

Pressing E performs a rectangular shape query **48px wide × 32px tall** centered in front of the player. Non-HEAVY objects in range receive an impulse of **400 units** in the direction `(facing, -0.3).normalized()` — forward and slightly upward. HEAVY objects receive damage but no impulse. 0.5s cooldown between kicks.

### Knockback

External forces (from rule engine effects, behavior APPLY_FORCE, etc.) are applied via `apply_external_impulse()`. The player's `EFFECTIVE_MASS` is intentionally very low (0.4) so impacts feel dramatic — an EXTREME force (800 units) produces roughly 5× jump velocity. A separate `_knockback` vector tracks accumulated impulse and decays at 800 px/s². During active knockback, player control authority is reduced proportionally — at 1000 px/s magnitude, control drops to the minimum 15%. This lets players fight back against knockback without making them fully helpless.

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
| Tags per object | 1-4 (enforced by LLM validator) |
| Signature behavior | 0-1 (optional, enforced by LLM validator) |
| Name length | 1-3 words (enforced by LLM validator) |


## Durability & Damage

Starting durability depends on tags:

| Tag | Durability |
|-----|-----------|
| BREAKABLE | 50 |
| RIGID | 200 |
| Default (neither) | 150 |

Priority: BREAKABLE checked first, then RIGID, then default.

**Damage-over-time (DOT)** — rule-defined; applied via DAMAGE effect with `tick_interval`/`tick_duration` fields:
- Ignition (HEAT_SOURCE + FLAMMABLE): 10 dmg/s for 5s (50 total)
- Spark ignition (ELECTRIC + FLAMMABLE): 8 dmg/s for 3s (24 total); also adds HEAT_SOURCE + HOT
- Corrosion (ACIDIC + BREAKABLE): 15 dmg/s for 3s (45 total)

DOT does not stack — a new DOT on an already-burning object replaces the existing one.

Objects reaching 0 durability are destroyed (`queue_free()`).

## Levels

3 puzzle levels using the `BaseLevel` pattern (extends Node2D). Each level has a spawn point, goal area, and objective text. Levels are designed to be solvable multiple ways — a gap can be bridged with a plank, crossed with a floating balloon, or bypassed with a bouncy trampoline.
