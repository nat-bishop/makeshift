# Game Design

## Core Concept

"Scribblenauts meets Terraria" — a 2D physics sandbox where players type text descriptions to create game objects. An LLM interprets descriptions into blueprints with a substance, optional element, tags, and behaviors. Gemini image generation produces sprites. Objects interact through a tag-based rule system and verb behavior system, enabling emergent puzzle-solving: fire melts ice, a wolf hunts prey, an acid spider corrodes metal.

Tags define what an object *is*; verbs define what it *does*. Each object has 1 substance, 0-1 element, 0-3 tags, and 0-4 behaviors. Substance and element automatically derive most traits — LLM tags are modifiers only.

## Tag System

12 LLM-visible tags (+ many substance/element-derived + 4 internal-only). In V2, most tags are automatically derived from substance and element — the LLM picks 0-3 independent modifiers that the substance doesn't cover.

### LLM-Visible Tags (V2)

| Tag | When to use |
|-----|------------|
| SHARP | Cutting edge or point — swords, claws, thorns |
| HEAVY | Dense/massive beyond substance default — anvils, safes |
| LIGHT | Very low mass — feathers, balloons, paper |
| BOUNCY | Elastic, high restitution — trampolines, springs |
| BREAKABLE | Fragile — overrides substance durability |
| STICKY | Adhesive — slows nearby to 25% speed |
| REFLECTIVE | Mirror-like — bounces heat/electricity/acid |
| EXPLOSIVE | Volatile — detonates under stress |
| FLYING | Defies gravity — birds, drones, ghosts |
| LIVING | Biological creature — enables behaviors |
| WET | Soaked — amplifies electric, freezes faster, resists fire |
| HOSTILE | Aggressive — damages nearby creatures in CLOSE field |

### Substance-Derived Traits (automatic)

| Substance | Auto traits |
|-----------|------------|
| metal | METALLIC, RIGID |
| wood | FLAMMABLE |
| stone | RIGID, HEAVY |
| glass | BREAKABLE, REFLECTIVE |
| rubber | BOUNCY, INSULATING |
| bone | RIGID |
| ceramic | BREAKABLE, INSULATING |
| cloth | FLAMMABLE, LIGHT |
| water | LIQUID, WET |
| oil | LIQUID, FLAMMABLE |
| slime | LIQUID, STICKY, TOXIC |
| ice | FROZEN, RIGID, COLD, BRITTLE |
| lava | MOLTEN, LIQUID, HEAT_SOURCE |
| fire | GAS, HEAT_SOURCE, HOT |
| smoke | GAS, LIGHT |
| flesh | *(none — add LIVING explicitly)* |

### Element-Derived Traits (optional)

| Element | Adds |
|---------|------|
| burning | HEAT_SOURCE, HOT |
| electric | ELECTRIC |
| magnetic | MAGNETIC |
| freezing | COLD |
| acidic | ACIDIC |
| toxic | TOXIC |
| windy | WIND_SOURCE |

### Internal-Only Tags (rule-added)

HOT (heat burn damage), GLOWING (smolder ignition + creature attraction), BRITTLE (freeze-then-shatter), CORRODED (acid-weakened, vulnerable to physical force).

WET (Environmental) is a state tag applied automatically by nearby LIQUID objects (15s duration). It amplifies interactions: ELECTRIC shock deals 45 dmg instead of 30, freezing occurs faster near COLD, and fire is resisted. Contradicts MOLTEN and HEAT_SOURCE. Physics effect: linear friction 0.1 (slippery when wet). Field tag (CLOSE, periodic).

HOSTILE (Special) is a danger-aura field tag — it deals 20 damage + knockback (150 force vs LIVING, 100 vs BREAKABLE) to everything in CLOSE range on a 2s tick. HOSTILE + HOSTILE clash rule deals 15 dmg to both sides + 120 force. This makes hostile objects into area-denial threats rather than simple contact hazards. Tags handle all contact damage; behaviors handle autonomous proactive actions.

STICKY (Surface) is a continuous field tag (CLOSE range) that slows everything nearby to 25% speed via the `sticky_slow` rule (APPLY_SLOW effect). Also deals 2 damage to LIVING things in the field (`sticky_living_struggle`) and catches fire from HEAT_SOURCE contact (`sticky_heat_fuel`). Area denial trap mechanic.

REFLECTIVE (Surface) bounces heat, electricity, and resists acid — the `reflective_acidic_resist` rule removes ACIDIC from the attacker on contact.

EXPLOSIVE is the highest-impact single tag: area damage on heat or electricity contact. Rules handle the detonation — no behavior needed.

### Contradiction Pairs (16)

Tags that can't coexist on the same object:

```
FROZEN↔MOLTEN    FROZEN↔HOT        FROZEN↔HEAT_SOURCE
COLD↔HOT         COLD↔MOLTEN       COLD↔HEAT_SOURCE
HEAVY↔LIGHT      LIQUID↔RIGID      GAS↔RIGID         GAS↔HEAVY
LIQUID↔GAS       METALLIC↔INSULATING
WET↔MOLTEN       WET↔HEAT_SOURCE
BRITTLE↔LIQUID   BRITTLE↔GAS
```

Enforced at runtime by `WorldMutations.apply_add_tag()` (auto-removes contradictory tag before adding). LLM tag validator also rejects contradictions with `ModelRetry` feedback.

## Rule System

59 `InteractionRule` definitions in `engine/rules_data.py`. Each rule specifies:
- Required tags on object A and/or B
- `execution_order` (higher fires first)
- Whether bidirectional (A↔B or only A→B)
- Whether cascade-eligible (can trigger chain reactions)
- `trigger_mode`: CONTACT (default) or FIELD
- Effects to apply

### Design Philosophy

**Intuitive**: Rules should match player intuition. Fire + flammable = ignite. Water + fire = extinguish. Sharp + breakable = damage.

**Chain reactions**: Cascade-eligible rules create emergent gameplay. Igniting one flammable object spreads HEAT_SOURCE to neighbors, which may ignite more flammable objects. Depth-limited to 3 to prevent infinite loops.

**Distance-based interactions**: ~28 of 59 rules are annotated `trigger_mode=FIELD`. These fire both at range (via `TagField`) and on direct contact. The rule declares *whether* an interaction works at distance; `FieldConfig` declares *how far* and *how* for the emitting tag. Separating these concerns avoids duplicating range values across rules that share the same emitting tag.

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
| Magnetic/Wind | MAGNETIC + METALLIC → attract, WIND_SOURCE + LIGHT/GAS/FLYING → push | No | Yes |
| Environmental | ACIDIC + BREAKABLE → corrode, TOXIC + LIVING → damage | No | Yes (TOXIC) |
| Brittle/Corroded | BRITTLE + HEAVY → 40 dmg shatter, CORRODED + SHARP → 40 dmg slice | No | No |
| Glowing | GLOWING + FLAMMABLE → smolder (adds HOT), GLOWING + LIVING → attract | No | Yes |
| Sticky | STICKY + any → APPLY_SLOW (25%), + LIVING → 2 dmg, + HEAT_SOURCE → fuel | Yes (fuel) | Yes |

### Field Modes

Rules with `trigger_mode=FIELD` execute via two paths:
- **Continuous** (WIND_SOURCE, MAGNETIC, STICKY): Per physics frame via `TagField._physics_process`. WIND_SOURCE/MAGNETIC use `apply_central_force()`. STICKY uses the `sticky_slow` rule's APPLY_SLOW effect to apply damping/speed reduction.
- **Periodic** (HEAT_SOURCE, HOT, ELECTRIC, COLD, TOXIC, LIQUID, HOSTILE, WET, GLOWING): `resolve_collision()` on a 2s timer. Full rule engine evaluation, subject to the 0.5s pair cooldown.

### Wildcard Rules

Rules with empty `tags_required_b` match any second object. Used for unconditional effects.

## Behavior System

LLM authors 0-4 verb behaviors per object. Each behavior = verb + freeform target string. The verb defines movement and action; the target string is semantically matched at runtime via embedding similarity.

### Verbs

| Verb | Movement | Action at range |
|------|----------|----------------|
| destroy | Toward target | Melee attack |
| eat | Toward target | Damage + heal self |
| investigate | Toward target (slow) | Stop at medium range |
| follow | Toward target | Maintain close distance |
| protect | Follow target | Attack threats near it |
| flee | Away from target | — |

### Target Matching

Each behavior's target string is embedded at creation time (via Ollama `qwen3-embedding:0.6b`). When objects enter the scene, their identity embedding (name + description + size + tags as natural language) is dot-product scored against each behavior's target embedding. Objects above threshold 0.5 become targets. Targets are re-scored when an object's tags change.

### Default Behavior

Only one implied behavior: LIVING + no explicit behaviors → `investigate → "interesting nearby objects"`.

### Design Examples

**Hungry wolf** (substance: flesh, element: null):
- Tags: LIVING
- Behaviors: destroy → "small prey animals", flee → "fire and loud noises"

**Fire sword** (substance: metal, element: burning):
- Tags: SHARP
- Behaviors: (none — tags handle everything)

**Acid spider** (substance: flesh, element: acidic):
- Tags: LIVING
- Behaviors: destroy → "small insects and prey", flee → "fire and larger creatures"

**Brave knight** (substance: flesh, element: null):
- Tags: LIVING, HOSTILE
- Behaviors: destroy → "monsters and evil creatures", protect → "villagers and innocents"

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

Walking into a `RigidBody2D` applies a continuous impulse of **80 units** in the collision direction. Only applies to `is_passively_pushable()` objects: tiny-sized, excluding HEAVY. Most objects require a deliberate kick to move.

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
| Substance per object | 1 (required) |
| Element per object | 0-1 (optional) |
| Tags per object | 0-3 (from `LLM_VISIBLE_TAGS_V2`, enforced by LLM validator) |
| Behaviors per object | 0-4 verb + target pairs (enforced by LLM validator) |
| Name length | 1-3 words (enforced by LLM validator) |


## Durability & Damage

Starting durability comes from the substance profile (`SubstanceProfile.durability`) modified by the BREAKABLE tag modifier (× 0.4). Substance base values range from 30 (fire) to 300 (stone). Examples: glass=40, wood=120, metal=250, flesh=150. The BREAKABLE tag multiplier applies on top of the substance base, so glass+BREAKABLE = 16 durability vs glass alone = 40.

**Damage-over-time (DOT)** — rule-defined; applied via DAMAGE effect with `tick_interval`/`tick_duration` fields:
- Ignition (HEAT_SOURCE + FLAMMABLE): 10 dmg/s for 5s (50 total)
- Spark ignition (ELECTRIC + FLAMMABLE): 8 dmg/s for 3s (24 total); also adds HEAT_SOURCE + HOT
- Corrosion (ACIDIC + BREAKABLE): 15 dmg/s for 3s (45 total)

DOT does not stack — a new DOT on an already-burning object replaces the existing one.

Objects reaching 0 durability are destroyed (`queue_free()`).

## Levels

3 puzzle levels using the `BaseLevel` pattern (extends Node2D). Each level has a spawn point, goal area, and objective text. Levels are designed to be solvable multiple ways — a gap can be bridged with a plank, crossed with a floating balloon, or bypassed with a bouncy trampoline.
