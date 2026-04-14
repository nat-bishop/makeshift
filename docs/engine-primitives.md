# Engine Primitives

Everything the LLM outputs must map onto something the engine can execute. This document is the reference for what those things are.

---

## Physics properties

Set at creation time. Each is 1 LLM call, 1-2 output tokens. All asked in parallel (~60ms wall time).

**Design principle:** Real-world physical quantities use real-world units (kg, cm) to leverage LLM training data grounding — the LLM knows "a sword weighs 1.5 kg" from training. Abstract game properties use 0-100 integer scales with named anchors.

| Property | Prompt format | Output | Engine mapping |
|---|---|---|---|
| **Mass** (kg) | "How heavy in kg? (ant=0.001, feather=0.01, apple=0.2, sword=1.5, human=70, car=1500, house=50000)" | 1 number (may be 2-4 tokens for decimals) | Direct. Clamped 0.001–100000 |
| **Height** (cm) | "How tall in cm? (ant=1, mouse=5, coin=2, sword=120, human=170, horse=200, house=800)" | 1 integer | Sprite scale + collision shape. cm → m for engine. Clamped 1–5000 |
| **Friction** (0–100) | "How grippy 0-100? (ice=0, metal=30, wood=50, rubber=90)" | 1 integer | PhysicsMaterial friction. 0-100 → 0.0-1.0 |
| **Bounce** (0–100) | "How bouncy 0-100? (clay=0, wood=20, tennis ball=70, super ball=99)" | 1 integer | PhysicsMaterial bounce. 0-100 → 0.0-1.0 |
| **Gravity** (0–100) | "Gravity pull 0-100? (balloon=5, smoke=15, ghost=30, feather=40, normal=50, rock=60, anvil=75)" | 1 integer | gravity_scale. 0-100 → -1.0 to 2.0 |

**Damping** is derived, not LLM-decided: `damping = height_cm / (mass_kg * 100 + 10)`. Light large things (feather) have high damping. Heavy small things (bullet) have low damping.

Mass uses real-world kg (decimal, 2-4 tokens) because LLM grounding in physical weight matters for answer quality. Height uses cm (integer, 1-2 tokens) — real-world grounded AND always an integer. All other properties are 0-100 integer scales with no real-world unit the LLM has strong priors about.

---

## Destructibility

One question, parallel with physics batch:

| Property | Prompt | Output | HP mapping |
|---|---|---|---|
| **Durability** (0–6) | "How durable? 0=fragile..6=indestructible (paper=0, wood=2, steel=4)" | 1 integer | 0→5, 1→15, 2→40, 3→80, 4→150, 5→300, 6→999999 |

No armor/damage-reduction mechanic — `durability` maps directly to a starting HP pool via `DURABILITY_HP` in `models/blueprint.py`. Tier 6 objects have effectively infinite HP.

---

---

## States (closed vocabulary)

State modifiers. Set at creation via `initial_states` (e.g., fire spawns burning) or spread at runtime via `StatePropagator` to susceptible neighbors. Each state has a distinct gameplay mechanic.

| # | State | Mechanic | Contradicts |
|---|---|---|---|
| 0 | none | — | — |
| 1 | burning | DOT 5 dmg/s, 10s duration. Skipped if burning is in `initial_states` (fire sources don't self-damage). Spreads to `susceptible_states=[1]` neighbors | frozen, wet |
| 2 | frozen | Immobilize (freeze=true) + brittle (2× incoming damage) | burning |
| 3 | wet | Friction → 0.05. Spreads to `susceptible_states=[3]` neighbors | burning |
| 4 | electrified | DOT 8 dmg/1.5s, 8s duration. Skipped if electrified is in `initial_states` (electrified sources don't self-damage). Spreads to `susceptible_states=[4]` neighbors | — |

This set is extensible — add new states when they have clear mechanics. States without game effects don't belong here.

### Contradiction table

Engine enforces on state add — adding a state automatically removes its contradictions:

```
burning:     removes [frozen, wet]
frozen:      removes [burning]
wet:         removes [burning]
electrified: no contradictions
```

### Visual effects

Each state maps to a known engine-side visual effect. No LLM involved — purely rendering. No sprite regeneration for state changes — particles and shaders handle all state visuals.

### State decay

States applied by interactions have a default decay timer (e.g., 10s). The state is removed automatically after the timer expires unless re-applied by the next `StatePropagator` tick. `initial_states` are applied with duration 0 (infinite — they persist until contradicted).

### Essential-state destruction

If an object has `initial_states` and all of them are removed (e.g., fire [burning=1] hit by water → burning removed by contradiction), the object is destroyed immediately. This is how fire is extinguished — no LLM destroy call needed.

### State stacking

Objects can have multiple states simultaneously (e.g., burning AND electrified is impossible — BURNING removes WET which chains, but burning AND frozen is also blocked). Contradictions prevent impossible combinations (see contradiction table above).

---

## Affordances

What happens when the player presses interact near an object. Three mechanics, each a chunk of engine code:

| # | Affordance | Input | Engine mechanic |
|---|---|---|---|
| 0 | **carry** | Player presses interact | Object hidden + physics frozen; player sprite swaps to pre-cached combined image. Drop/throw restores original sprites and unfreezes. |
| 1 | **mount** | Player presses interact | Same sprite-swap as carry. Combined image shows player riding the object. |
| 2 | **climb** | Player overlaps object | Player vertical velocity modified. Player moves upward while overlapping. No reparenting. |

One LLM call at creation, 1 token:
```
"When a player interacts with [horse]:
 0=carry it  1=ride it  2=climb it  3=nothing"
→ 1
```

### Carry/mount mechanics (sprite-swap)

- **Pickup/mount:** Object `visible=false`, `freeze=true`, `collision_layer/mask=0`. Player sprite swaps to pre-cached combined image (generated at object creation time, delivered via `combined_sprite_ready` WS message)
- **Throw:** Release object, restore visibility + physics, apply impulse in aim direction
- **Drop:** Same as throw, zero impulse
- **Object destroyed while held:** `tree_exiting` signal restores player sprite automatically
- Combined sprite prompt: `"{player} carrying/riding {object}"` — generated at creation, cached by SHA-256 of prompt

### Climb mechanics

- **While overlapping:** Player gains upward velocity (overrides gravity)
- **On exit:** Normal gravity resumes

### Some interactions are just carry + behavior outcome

No separate affordance needed for:
- **Drinkable/edible:** carry + behavior action=heal on player
- **Throwable:** carry + throw (release with impulse)
- **Pushable:** mass too high for carry → engine applies force instead of reparenting

---

## Object behavior (per-pair)

All autonomous objects share one system — active creatures (wolf, zombie) AND reactive objects (bomb, fan, acid). Each subject×object relationship is evaluated independently at spawn time.

**Active objects** (movement=approach/flee) move toward or away from targets and execute composite actions on contact.

**Reactive objects** (movement=ignore, priority>0) never move but act when a target enters CONTACT_RANGE.

### Movement patterns

| # | Movement | Engine behavior |
|---|---|---|
| 0 | **approach** | Move toward target, stop at contact |
| 1 | **flee** | Move away from target |
| 2 | **ignore** | No movement reaction |

### Actions (composite)

| # | Action | Amount | State modifier | Force modifier |
|---|---|---|---|---|
| 0 | **nothing** | — | — | — |
| 1 | **damage** | 0-100 | add/remove state (optional) | push (optional) |
| 2 | **heal** | 0-100 | add/remove state (optional) | — |
| 3 | **consume** | 0-100 | add/remove state (optional) | — |
| 4 | **push** | 0-100 | — | — |

A single interaction can combine: primary action + state modifier (add/remove) + force modifier (knockback on damage only). A wolf can damage + push + add_state(burning) simultaneously. Pull is not supported — push/throw force is now in the action enum directly.

### Staged evaluation

See [architecture.md](architecture.md) for the full staged evaluation flow. Three sequential stages (movement+priority → action → parameters), each parallel internally, each seeding context to the next. 1 token per call.

### Priority resolution — utility scoring

Active objects pick ONE target per frame using utility scoring. Same pattern as The Sims — the object should look like it's making a decision ("going for the donut"), not drifting at a blended angle.

```
For each pair with movement ≠ ignore:
  utility = priority_weight / (1 + distance / perception_range)
  if movement == flee:
    utility *= 1.5   # survival bias

Pick highest utility pair.
  flee → move away from that object
  approach → move toward that object
```

`PRIORITY_WEIGHTS = {0: 0.0, 1: 25.0, 2: 60.0, 3: 100.0}`. The 1.5× flee multiplier ensures survival slightly overrides desire at equal priority and distance.

If creatures need obstacle avoidance (curve around garlic to reach human), that's a pathfinding layer on top — not priority resolution. Defer until playtesting shows it's needed.

---

## State properties (replaces Fields)

Instead of `has_field`/`field_range_cm`, objects declare what states they spawn with and what states can spread to them. Eight boolean creation questions:

**Initial states** (does this object spawn with this state?):
- `initially_burning` — fire, campfire, lava
- `initially_frozen` — ice, frozen lake
- `initially_wet` — water, rain, puddle
- `initially_electrified` — lightning bolt, electric eel

**Susceptible states** (can this state spread to this object?):
- `catches_fire` — wood, paper, cloth
- `can_freeze` — water, wet objects
- `gets_wet` — dry materials near water
- `conducts_electricity` — metal, water

The `StatePropagator` component (attached to every game object) ticks every 2s when the owner has active states. It spreads each active state to any overlapping body that has that state ID in `susceptible_states`. Radius = `BASE_RADIUS × scale_from_height(height_cm)` — a bonfire spreads further than a candle.

---

## Destruction

When an object reaches 0 HP, it plays a death animation (shrink, fade, particle burst) and is removed from the scene. No runtime LLM calls or image generation.

See [future-features.md](future-features.md) for destruction remains (generating "pile of charred splinters" sprites).
